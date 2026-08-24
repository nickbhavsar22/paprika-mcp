"""Tests for the hardened API layer, caching, and the thumbnail chain.

Every external call is mocked — this suite never touches the Paprika API, an
image search, or an image generator.
"""

import base64
import io
import os
import types
import unittest
from unittest.mock import MagicMock, patch

import requests
from paprika_recipes.remote import RemoteRecipe

from paprika_mcp import photo, utils
from paprika_mcp.recipe_maintenance import (
    _extract_link_image,
    candidate_thumbnail,
    looks_like_photo,
    source_thumbnail,
    verify_image_dimensions,
    web_image_search,
    web_image_search_detailed,
)
from paprika_mcp.tools.update_grocery import _as_bool


def make_recipe(**overrides) -> RemoteRecipe:
    fields = {
        "name": "Lasagna",
        "ingredients": "",
        "directions": "",
        "description": "",
        "notes": "",
        "source": "",
        "source_url": "",
        "image_url": "",
    }
    fields.update(overrides)
    return RemoteRecipe(**fields)


def _never(*args, **kwargs):
    """Stand-in for a thumbnail source that finds nothing."""
    return None


class FindRecipeByIdTests(unittest.TestCase):
    """A by-UID lookup must not download the whole recipe library."""

    def _remote(self, count=50):
        remote = MagicMock()
        remote._get_remote_recipe_identifiers.return_value = [
            types.SimpleNamespace(uid=f"U{i}", hash=f"H{i}") for i in range(count)
        ]
        remote.get_recipe_by_id.return_value = "RECIPE"
        return remote

    def test_fetches_only_the_matching_recipe(self):
        remote = self._remote()
        self.assertEqual(utils.find_recipe_by_id(remote, "U30"), "RECIPE")
        self.assertEqual(remote._get_remote_recipe_identifiers.call_count, 1)
        remote.get_recipe_by_id.assert_called_once_with("U30", "H30")

    def test_unknown_uid_returns_none_without_fetching(self):
        remote = self._remote()
        self.assertIsNone(utils.find_recipe_by_id(remote, "MISSING"))
        remote.get_recipe_by_id.assert_not_called()


class APIErrorSurfaceTests(unittest.TestCase):
    """A failed fetch must never be indistinguishable from an empty result."""

    def setUp(self):
        utils.invalidate_cache()

    def tearDown(self):
        utils.invalidate_cache()

    def test_network_failure_raises_rather_than_returning_empty(self):
        with patch.object(utils, "_get_session") as session:
            session.return_value.get.side_effect = requests.ConnectionError("down")
            for fetch in (
                utils.get_groceries,
                utils.get_categories,
                utils.get_grocery_lists,
                utils.get_grocery_aisles,
                utils.get_meals,
                utils.get_meal_types,
            ):
                utils.invalidate_cache()
                with self.subTest(fetch=fetch.__name__):
                    with self.assertRaises(utils.PaprikaAPIError):
                        fetch("token")

    def test_error_body_in_a_200_response_is_detected(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"error": {"message": "invalid token"}}
        with patch.object(utils, "_get_session") as session:
            session.return_value.get.return_value = response
            with self.assertRaises(utils.PaprikaAPIError) as ctx:
                utils.get_groceries("token")
        self.assertIn("invalid token", str(ctx.exception))

    def test_genuinely_empty_result_is_still_empty(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"result": []}
        with patch.object(utils, "_get_session") as session:
            session.return_value.get.return_value = response
            self.assertEqual(utils.get_groceries("token"), [])


class CacheTests(unittest.TestCase):
    def setUp(self):
        utils.invalidate_cache()

    def tearDown(self):
        utils.invalidate_cache()

    def test_results_are_cached_then_invalidated_and_expired(self):
        payload = {"result": [{"uid": "A1", "name": "Produce", "order_flag": 1}]}
        with patch.object(utils, "_api_get", return_value=payload) as api:
            utils.get_grocery_aisles("t")
            utils.get_grocery_aisles("t")
            self.assertEqual(api.call_count, 1, "second call should hit the cache")

            utils.invalidate_cache("grocery_aisles")
            utils.get_grocery_aisles("t")
            self.assertEqual(api.call_count, 2, "invalidation should force a refetch")

            # Simulate an entry older than the TTL.
            utils._ttl_cache["grocery_aisles"] = (0.0, [])
            utils.get_grocery_aisles("t")
            self.assertEqual(api.call_count, 3, "expired entry should refetch")


class AisleResolutionTests(unittest.TestCase):
    def test_unknown_aisle_returns_none_so_callers_can_warn(self):
        aisles = [{"uid": "A1", "name": "Produce"}]
        with patch.object(utils, "get_grocery_aisles", return_value=aisles):
            self.assertEqual(utils.resolve_aisle_uid("produce", "t"), "A1")
            self.assertIsNone(utils.resolve_aisle_uid("Nonexistent", "t"))


class BooleanCoercionTests(unittest.TestCase):
    def test_coerces_common_client_representations(self):
        # A list, not a dict: True/1 and False/0 collide as dict keys, which
        # would silently drop the int cases.
        cases = [
            (True, True),
            (False, False),
            ("true", True),
            ("FALSE", False),
            ("yes", True),
            ("no", False),
            ("1", True),
            ("0", False),
            (1, True),
            (0, False),
            ("banana", None),
            (None, None),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertIs(_as_bool(value), expected)


class ImageBase64Tests(unittest.TestCase):
    """Generated images sometimes arrive as base64 rather than a hosted URL."""

    @classmethod
    def setUpClass(cls):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(buffer, format="JPEG")
        cls.jpeg = buffer.getvalue()
        cls.encoded = base64.b64encode(cls.jpeg).decode()

    def test_decodes_plain_data_uri_and_wrapped_base64(self):
        wrapped = "\n".join(
            self.encoded[i : i + 60] for i in range(0, len(self.encoded), 60)
        )
        for label, value in (
            ("plain", self.encoded),
            ("data URI", f"data:image/jpeg;base64,{self.encoded}"),
            ("wrapped", wrapped),
        ):
            with self.subTest(label=label):
                self.assertEqual(photo.decode_image_base64(value), self.jpeg)

    def test_rejects_invalid_input(self):
        for value in ("not base64!!!", ""):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    photo.decode_image_base64(value)

    def test_resolve_image_bytes_routes_base64(self):
        raw, label = photo.resolve_image_bytes({"image_base64": self.encoded})
        self.assertEqual(raw, self.jpeg)
        self.assertEqual(label, "generated:base64")

    def test_decoded_bytes_normalize_to_jpeg(self):
        normalized = photo.normalize_to_jpeg(photo.decode_image_base64(self.encoded))
        self.assertTrue(normalized.startswith(b"\xff\xd8"))


class WebImageSearchTests(unittest.TestCase):
    """The Pexels tier is optional and must never break the chain."""

    @staticmethod
    def _pexels_response(**src):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "photos": [
                {
                    "src": src or {"large": "https://img/x.jpg"},
                    "photographer": "Ada Cook",
                    "url": "https://pexels.com/photo/1",
                }
            ]
        }
        return response

    def test_returns_none_when_not_configured(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("PEXELS_API_KEY", None)
            self.assertIsNone(web_image_search("lasagna"))

    def test_returns_image_url_when_configured(self):
        with patch.dict("os.environ", {"PEXELS_API_KEY": "k"}):
            with patch(
                "paprika_mcp.recipe_maintenance.requests.get",
                return_value=self._pexels_response(),
            ):
                self.assertEqual(web_image_search("lasagna"), "https://img/x.jpg")

    def test_sends_the_key_as_an_authorization_header(self):
        with patch.dict("os.environ", {"PEXELS_API_KEY": "secret-key"}):
            with patch(
                "paprika_mcp.recipe_maintenance.requests.get",
                return_value=self._pexels_response(),
            ) as get:
                web_image_search("lasagna")
        headers = get.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "secret-key")

    def test_falls_back_through_available_image_sizes(self):
        # 'large' missing: should still find a usable size rather than give up.
        with patch.dict("os.environ", {"PEXELS_API_KEY": "k"}):
            with patch(
                "paprika_mcp.recipe_maintenance.requests.get",
                return_value=self._pexels_response(original="https://img/orig.jpg"),
            ):
                self.assertEqual(web_image_search("lasagna"), "https://img/orig.jpg")

    def test_detailed_search_returns_attribution(self):
        with patch.dict("os.environ", {"PEXELS_API_KEY": "k"}):
            with patch(
                "paprika_mcp.recipe_maintenance.requests.get",
                return_value=self._pexels_response(),
            ):
                detail = web_image_search_detailed("lasagna")
        self.assertEqual(detail["photographer"], "Ada Cook")
        self.assertEqual(detail["source_page"], "https://pexels.com/photo/1")

    def test_empty_result_set_returns_none(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"photos": []}
        with patch.dict("os.environ", {"PEXELS_API_KEY": "k"}):
            with patch(
                "paprika_mcp.recipe_maintenance.requests.get", return_value=response
            ):
                self.assertIsNone(web_image_search("nonexistent dish"))

    def test_network_failure_returns_none_instead_of_raising(self):
        with patch.dict("os.environ", {"PEXELS_API_KEY": "k"}):
            with patch(
                "paprika_mcp.recipe_maintenance.requests.get",
                side_effect=requests.Timeout(),
            ):
                self.assertIsNone(web_image_search("lasagna"))


class SiteChromeRejectionTests(unittest.TestCase):
    """A page's favicon or logo must never become a recipe thumbnail.

    Regression: a real recipe (Chicken Tandoori) picked up
    'cropped-KITCHENMAILogo-...-32x32.png' from its source page's
    <link rel="icon"> and reported it as a 0.90-confidence candidate.
    """

    def test_rejects_site_chrome(self):
        rejected = [
            "https://kitchenmai.com/wp-content/uploads/2018/12/"
            "cropped-KITCHENMAILogo-e1545311302616-3-32x32.png",
            "https://site.com/favicon.ico",
            "https://site.com/apple-touch-icon.png",
            "https://site.com/android-chrome-192x192.png",
            "https://site.com/assets/site-logo.png",
            "https://site.com/brand.svg",
            "https://site.com/img/thumb-16x16.png",
            "https://site.com/sprite.png",
        ]
        for url in rejected:
            with self.subTest(url=url):
                self.assertFalse(looks_like_photo(url))

    def test_accepts_real_photos(self):
        accepted = [
            "https://www.onceuponachef.com/images/2012/09/Chicken-Kabobs-1200x1480.jpg",
            "https://feelgoodfoodie.net/wp-content/uploads/2023/04/Hummus-11.jpg",
            "https://images.pexels.com/photos/14286683/pexels-photo.jpeg?auto=compress&w=940",
        ]
        for url in accepted:
            with self.subTest(url=url):
                self.assertTrue(looks_like_photo(url))

    def test_none_and_empty_are_rejected(self):
        self.assertFalse(looks_like_photo(None))
        self.assertFalse(looks_like_photo(""))

    def test_link_rel_icon_is_not_extracted(self):
        html_text = '<link rel="icon" href="/favicon-32x32.png">'
        self.assertIsNone(_extract_link_image(html_text))

    def test_link_rel_image_src_is_still_extracted(self):
        html_text = '<link rel="image_src" href="/photos/dish.jpg">'
        self.assertEqual(_extract_link_image(html_text), "/photos/dish.jpg")

    def test_source_thumbnail_drops_a_favicon_og_image(self):
        page = '<meta property="og:image" content="https://s.com/favicon.ico">'
        with patch("paprika_mcp.recipe_maintenance._fetch_html", return_value=page):
            self.assertIsNone(source_thumbnail("https://s.com/recipe"))

    def test_source_thumbnail_keeps_a_real_og_image(self):
        page = '<meta property="og:image" content="https://s.com/dish-1200x800.jpg">'
        with patch("paprika_mcp.recipe_maintenance._fetch_html", return_value=page):
            self.assertEqual(
                source_thumbnail("https://s.com/recipe"),
                "https://s.com/dish-1200x800.jpg",
            )

    def test_verify_rejects_an_image_that_is_too_small(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (32, 32), "blue").save(buf, format="PNG")
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.raw.read.return_value = buf.getvalue()
        with patch(
            "paprika_mcp.recipe_maintenance.requests.get", return_value=response
        ):
            self.assertFalse(verify_image_dimensions("https://s.com/photo.jpg"))

    def test_verify_accepts_a_large_image(self):
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (800, 600), "green").save(buf, format="JPEG")
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.raw.read.return_value = buf.getvalue()
        with patch(
            "paprika_mcp.recipe_maintenance.requests.get", return_value=response
        ):
            self.assertTrue(verify_image_dimensions("https://s.com/photo.jpg"))

    def test_verify_rejects_on_network_failure(self):
        with patch(
            "paprika_mcp.recipe_maintenance.requests.get",
            side_effect=requests.Timeout(),
        ):
            self.assertFalse(verify_image_dimensions("https://s.com/photo.jpg"))


class ThumbnailPriorityTests(unittest.TestCase):
    """Recipe-specific sources must outrank generic ones."""

    def test_existing_thumbnail_wins(self):
        candidate = candidate_thumbnail(
            make_recipe(image_url="https://have.jpg"),
            fetch_source_image=_never,
            fetch_web_image=_never,
            fetch_wikimedia_image=_never,
        )
        self.assertEqual(candidate.source, "existing")

    def test_source_page_beats_stock_photo(self):
        candidate = candidate_thumbnail(
            make_recipe(source_url="https://site/recipe"),
            fetch_source_image=lambda url: "https://og.jpg",
            fetch_web_image=lambda q: "https://web.jpg",
            fetch_wikimedia_image=lambda q: "https://wiki.jpg",
        )
        self.assertEqual(candidate.source, "source_page")
        self.assertEqual(candidate.url, "https://og.jpg")

    def test_stock_photo_beats_wikimedia(self):
        candidate = candidate_thumbnail(
            make_recipe(),
            fetch_source_image=_never,
            fetch_web_image=lambda q: "https://web.jpg",
            fetch_wikimedia_image=lambda q: "https://wiki.jpg",
        )
        self.assertEqual(candidate.source, "stock_photo")

    def test_wikimedia_is_the_last_free_tier(self):
        candidate = candidate_thumbnail(
            make_recipe(),
            fetch_source_image=_never,
            fetch_web_image=_never,
            fetch_wikimedia_image=lambda q: "https://wiki.jpg",
        )
        self.assertEqual(candidate.source, "wikimedia")

    def test_returns_none_when_no_free_source_has_an_image(self):
        self.assertIsNone(
            candidate_thumbnail(
                make_recipe(),
                fetch_source_image=_never,
                fetch_web_image=_never,
                fetch_wikimedia_image=_never,
            )
        )


class ErrorSanitizationTests(unittest.IsolatedAsyncioTestCase):
    """Raw exception text must stay in the log, not the tool response."""

    async def _call(self, handler):
        from paprika_mcp.server import call_tool
        from paprika_mcp.tools import TOOLS

        original = TOOLS["list_groceries"]["handler"]
        TOOLS["list_groceries"]["handler"] = handler
        try:
            with self.assertLogs("paprika_mcp.server", level="ERROR"):
                result = await call_tool("list_groceries", {})
        finally:
            TOOLS["list_groceries"]["handler"] = original
        return result[0].text

    async def test_unexpected_error_does_not_leak_its_message(self):
        secret = "password=hunter2 token=eyJabc123"

        async def boom(args):
            raise RuntimeError(secret)

        text = await self._call(boom)
        self.assertNotIn("hunter2", text)
        self.assertNotIn("eyJabc123", text)
        self.assertIn("RuntimeError", text)

    async def test_api_outage_is_not_reported_as_no_data(self):
        async def outage(args):
            raise utils.PaprikaAPIError("upstream 503")

        text = (await self._call(outage)).lower()
        self.assertIn("empty", text)
        self.assertIn("do not", text)


class RemoteCachingTests(unittest.TestCase):
    def setUp(self):
        utils.reset_remote()

    def tearDown(self):
        utils.reset_remote()

    def test_remote_is_built_once_and_reset_forces_reauth(self):
        with patch.object(utils, "_build_remote", return_value="REMOTE") as build:
            utils.get_remote()
            utils.get_remote()
            utils.get_remote()
            self.assertEqual(build.call_count, 1)

            utils.reset_remote()
            utils.get_remote()
            self.assertEqual(build.call_count, 2)


if __name__ == "__main__":
    unittest.main()

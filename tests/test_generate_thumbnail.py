"""Tests for generate_thumbnail. OpenAI and Paprika are mocked throughout:
requests.post is patched for every test, so no test can spend money."""

import asyncio
import base64
import io
import os
import unittest
from unittest.mock import MagicMock, patch

import requests
from paprika_recipes.remote import RemoteRecipe
from PIL import Image

from paprika_mcp import photo
from paprika_mcp.prompts.set_recipe_thumbnail import INSTRUCTIONS
from paprika_mcp.tools import TOOLS
from paprika_mcp.tools.generate_thumbnail import (
    MAX_DESCRIPTION_CHARS,
    OPENAI_IMAGES_URL,
    STYLE,
    build_image_prompt,
    generate_thumbnail_tool,
)

MODULE = "paprika_mcp.tools.generate_thumbnail"


def png_b64() -> str:
    out = io.BytesIO()
    Image.new("RGB", (64, 64), "orange").save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode()


def ok_response() -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": [{"b64_json": png_b64()}]}
    return resp


def run(args) -> str:
    return asyncio.run(generate_thumbnail_tool(args))[0].text


class BuildImagePromptTests(unittest.TestCase):
    def test_includes_name_description_and_style(self):
        prompt = build_image_prompt("Lasagna", "Layered  pasta\nwith ricotta.")
        self.assertIn("Professional food photography of Lasagna.", prompt)
        self.assertIn("Layered pasta with ricotta.", prompt)
        self.assertIn(STYLE, prompt)

    def test_long_description_is_truncated_and_empty_is_omitted(self):
        prompt = build_image_prompt("Soup", "x" * 1000)
        self.assertIn("x" * MAX_DESCRIPTION_CHARS + "\n", prompt)
        self.assertNotIn("x" * (MAX_DESCRIPTION_CHARS + 1), prompt)
        self.assertEqual(build_image_prompt("Soup", None).count("\n"), 2)

    def test_higgsfield_prompt_template_matches_the_tool_style(self):
        # The prompt's template is used for the Higgsfield tier; keep it in sync.
        self.assertIn(" ".join(STYLE.split()), " ".join(INSTRUCTIONS.split()))


class GenerateThumbnailTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"})
        env.start()
        for var in ("OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_QUALITY"):
            os.environ.pop(var, None)
        self.post = patch(f"{MODULE}.requests.post", return_value=ok_response())
        self.post = self.post.start()
        self.recipe = RemoteRecipe(
            uid="U1", name="Lasagna", description="Layered pasta bake.", photo=""
        )
        self.remote = MagicMock()
        patch(f"{MODULE}.get_remote", return_value=self.remote).start()
        self.find = patch(f"{MODULE}.find_recipe_by_id", return_value=self.recipe)
        self.find = self.find.start()
        self.attach = patch(
            f"{MODULE}.attach_photo_bytes",
            return_value={"photo_filename": "X.jpg", "photo_hash": "H", "size_kb": 9},
        ).start()
        self.addCleanup(patch.stopall)

    def test_generates_and_attaches_with_defaults(self):
        text = run({"id": "U1"})
        url = self.post.call_args.args[0]
        kwargs = self.post.call_args.kwargs
        self.assertEqual(url, OPENAI_IMAGES_URL)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(kwargs["json"]["model"], "gpt-image-2")
        self.assertEqual(kwargs["json"]["quality"], "medium")
        self.assertEqual(kwargs["json"]["size"], "1024x1024")
        self.assertIn("Layered pasta bake.", kwargs["json"]["prompt"])
        remote, recipe, jpeg, label = self.attach.call_args.args
        self.assertIs(recipe, self.recipe)
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))  # normalized to JPEG
        self.assertEqual(label, "generated:gpt-image-2")
        self.assertIn("added it on 'Lasagna'", text)

    def test_model_quality_and_description_can_be_overridden(self):
        os.environ["OPENAI_IMAGE_MODEL"] = "gpt-image-1.5"
        run({"id": "U1", "quality": "high", "dish_description": "Golden top."})
        payload = self.post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "gpt-image-1.5")
        self.assertEqual(payload["quality"], "high")
        self.assertIn("Golden top.", payload["prompt"])
        self.assertNotIn("Layered pasta bake.", payload["prompt"])

    def test_missing_key_falls_back_without_spending(self):
        del os.environ["OPENAI_API_KEY"]
        text = run({"id": "U1"})
        self.assertIn("not configured", text)
        self.assertIn("Higgsfield", text)
        self.post.assert_not_called()
        self.find.assert_not_called()

    def test_invalid_quality_and_missing_id_are_rejected(self):
        self.assertIn("'quality' must be one of", run({"id": "U1", "quality": "ultra"}))
        self.assertIn("'id' is required", run({}))
        self.post.assert_not_called()

    def test_existing_thumbnail_is_kept_unless_replace(self):
        self.recipe.photo = "OLD.jpg"
        text = run({"id": "U1"})
        self.assertIn("already has a thumbnail", text)
        self.post.assert_not_called()
        self.assertIn("replaced it", run({"id": "U1", "replace": True}))
        self.post.assert_called_once()

    def test_unknown_recipe_is_reported_before_spending(self):
        self.find.return_value = None
        self.assertIn("No recipe found", run({"id": "NOPE"}))
        self.post.assert_not_called()

    def test_openai_error_is_surfaced_with_the_higgsfield_prompt(self):
        resp = MagicMock(status_code=400)
        resp.json.return_value = {"error": {"message": "Your request was blocked."}}
        self.post.return_value = resp
        text = run({"id": "U1"})
        self.assertIn("OpenAI returned 400: Your request was blocked.", text)
        self.assertIn("Professional food photography of Lasagna.", text)
        self.attach.assert_not_called()

    def test_network_failure_is_surfaced(self):
        self.post.side_effect = requests.ConnectionError("down")
        text = run({"id": "U1"})
        self.assertIn("could not reach OpenAI (ConnectionError)", text)
        self.attach.assert_not_called()

    def test_upload_failure_holds_the_paid_image_for_retry(self):
        self.attach.side_effect = RuntimeError("Paprika 500")
        text = run({"id": "U1"})
        code = text.split("upload code ")[1].split()[0]
        self.assertIn(f"upload_code='{code}'", text)
        self.assertTrue(photo.pop_staged(code).startswith(b"\xff\xd8"))

    def test_tool_is_registered(self):
        self.assertIs(TOOLS["generate_thumbnail"]["handler"], generate_thumbnail_tool)


if __name__ == "__main__":
    unittest.main()

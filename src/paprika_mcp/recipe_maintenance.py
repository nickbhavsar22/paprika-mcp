"""Recipe audit and cleanup helpers for Paprika recipes."""

from __future__ import annotations

import html
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from paprika_recipes.remote import RemoteRecipe

URL_RE = re.compile(r"https?://[^\s<>\]]+")
HTTP_HEADERS = {"User-Agent": "paprika-mcp/0.1 recipe-thumbnail-audit"}
YOUTUBE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})",
    re.IGNORECASE,
)
TIMESTAMP_RE = re.compile(
    r"^\s*(?:\(?\s*)?(?:\d{1,2}:)?\d{1,2}:\d{2}(?:[:.]\d{2})?(?:\s*\)?)?\s*[-–—:)]*\s*"
)
HTML_BREAK_RE = re.compile(r"(?i)<br\s*/?>")
HTML_TAG_RE = re.compile(r"<[^>]+>")
BULLET_RE = re.compile(r"^\s*[-*•·]\s+")
NUMBERED_RE = re.compile(r"^\s*(?:\(?\d+[.)]\s+|\d+\s*[-:]\s+)")
YIELD_HINT_RE = re.compile(
    r"\b(?:serves?|yield|makes|serving size)\s*[:\-]?\s*(\d+(?:\.\d+)?(?:/\d+)?)",
    re.IGNORECASE,
)
FOOD_WORDS = {
    "bake",
    "bread",
    "cake",
    "chicken",
    "cocktail",
    "cookie",
    "drink",
    "fish",
    "food",
    "gin",
    "martini",
    "meal",
    "pasta",
    "pie",
    "recipe",
    "salad",
    "soup",
    "stew",
    "vodka",
}


@dataclass(slots=True)
class RecipeFinding:
    code: str
    message: str
    severity: str = "info"


@dataclass(slots=True)
class RecipeChange:
    field: str
    before: str
    after: str
    reason: str


@dataclass(slots=True)
class ThumbnailCandidate:
    url: str
    source: str
    confidence: float
    notes: str = ""


@dataclass(slots=True)
class RecipeAudit:
    uid: str
    name: str
    has_thumbnail: bool
    status: str
    findings: list[RecipeFinding] = field(default_factory=list)
    changes: list[RecipeChange] = field(default_factory=list)
    thumbnail: ThumbnailCandidate | None = None
    serving_suggestion: str | None = None


@dataclass(slots=True)
class RecipePlan:
    uid: str
    name: str
    updates: dict[str, Any] = field(default_factory=dict)
    audit: RecipeAudit | None = None


def strip_html_tags(text: str) -> str:
    """Remove HTML tags while preserving paragraph boundaries."""
    if not text:
        return ""

    normalized = html.unescape(text)
    normalized = HTML_BREAK_RE.sub("\n", normalized)
    normalized = re.sub(r"</(p|div|li|tr|h[1-6])\s*>", "\n", normalized, flags=re.I)
    normalized = HTML_TAG_RE.sub("", normalized)
    return normalized


def normalize_text_block(text: str) -> str:
    """Normalize a text block for line-based cleanup."""
    text = strip_html_tags(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def extract_urls(text: str) -> list[str]:
    """Return URLs found in a text block."""
    return [unquote(match.group(0)) for match in URL_RE.finditer(text or "")]


def extract_youtube_url(text: str) -> str | None:
    """Find the first YouTube URL in text."""
    for url in extract_urls(text):
        if "youtube.com" in url.lower() or "youtu.be" in url.lower():
            return url
    return None


def extract_youtube_id(url: str | None) -> str | None:
    """Extract a YouTube video ID from a URL."""
    if not url:
        return None

    match = YOUTUBE_RE.search(url)
    if match:
        return match.group(1)

    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc.lower():
        query = parse_qs(parsed.query)
        values = query.get("v")
        if values:
            return values[0]
    return None


def youtube_thumbnail(url: str | None) -> str | None:
    """Build a thumbnail URL for a YouTube video."""
    video_id = extract_youtube_id(url)
    if not video_id:
        return None
    return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"


def collapse_whitespace(text: str) -> str:
    """Collapse repeated blank lines and trim trailing whitespace."""
    lines = [line.rstrip() for line in text.split("\n")]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        blank = not line.strip()
        if blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = blank
    return "\n".join(collapsed).strip()


def _clean_body_lines(text: str, *, bullets: bool) -> list[str]:
    cleaned_lines: list[str] = []

    for raw_line in normalize_text_block(text).split("\n"):
        line = raw_line.strip()
        if not line:
            continue

        line = TIMESTAMP_RE.sub("", line)
        line = BULLET_RE.sub("", line)
        line = NUMBERED_RE.sub("", line)
        line = re.sub(
            r"^\s*(ingredients?|directions?|instructions?)\s*[:\-]?\s*$",
            "",
            line,
            flags=re.I,
        )
        line = line.strip()
        if not line:
            continue

        if bullets:
            cleaned_lines.append(f"- {line}")
        else:
            cleaned_lines.append(line)

    return cleaned_lines


def clean_ingredients(text: str) -> str:
    """Normalize ingredients into a simple bullet list."""
    lines = _clean_body_lines(text, bullets=True)
    return collapse_whitespace("\n".join(lines))


def clean_instructions(text: str) -> str:
    """Normalize instructions into a numbered list."""
    raw = normalize_text_block(text)
    if not raw:
        return ""

    chunks: list[str] = []
    current: list[str] = []

    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
            continue

        stripped = TIMESTAMP_RE.sub("", stripped)
        stripped = BULLET_RE.sub("", stripped)
        stripped = NUMBERED_RE.sub("", stripped)
        stripped = stripped.strip()
        if not stripped:
            continue
        current.append(stripped)

    if current:
        chunks.append(" ".join(current).strip())

    if not chunks:
        chunks = [line for line in _clean_body_lines(raw, bullets=False) if line]

    numbered = [f"{index + 1}. {chunk}" for index, chunk in enumerate(chunks) if chunk]
    return collapse_whitespace("\n".join(numbered))


def extract_yield_hint(*texts: str) -> str | None:
    """Look for a clear yield or serving hint in free text."""
    for text in texts:
        if not text:
            continue
        match = YIELD_HINT_RE.search(text)
        if match:
            return match.group(1)
    return None


def build_description_with_links(
    description: str, source_url: str | None, video_url: str | None
) -> tuple[str, list[str]]:
    """Append source and video links to the description if missing."""
    description = normalize_text_block(description)
    additions: list[str] = []
    existing_urls = {url.lower() for url in extract_urls(description)}

    if source_url and source_url.lower() not in existing_urls:
        additions.append(f"Source: {source_url}")
    if video_url and video_url.lower() not in existing_urls:
        additions.append(f"Video: {video_url}")

    if not additions:
        return description, []

    if description:
        description = f"{description}\n\n" + "\n".join(additions)
    else:
        description = "\n".join(additions)

    return collapse_whitespace(description), additions


def parse_servings_value(servings: str | None) -> float | None:
    """Parse a simple serving-size value from text."""
    if not servings:
        return None

    match = re.search(r"(\d+(?:\.\d+)?(?:/\d+)?)", servings)
    if not match:
        return None

    value = match.group(1)
    if "/" in value and "." not in value:
        numerator, denominator = value.split("/", 1)
        try:
            return float(numerator) / float(denominator)
        except ValueError:
            return None

    try:
        return float(value)
    except ValueError:
        return None


def _fetch_html(url: str, timeout: int = 15) -> str | None:
    try:
        response = requests.get(url, headers=HTTP_HEADERS, timeout=timeout)
        response.raise_for_status()
        return cast(str, response.text)
    except requests.RequestException:
        return None


def _extract_meta_content(html_text: str, names: tuple[str, ...]) -> str | None:
    patterns = [
        re.compile(
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']',
            re.IGNORECASE,
        )
        for name in names
    ]
    for pattern in patterns:
        match = pattern.search(html_text)
        if match:
            return html.unescape(match.group(1))
    return None


def _extract_link_image(html_text: str) -> str | None:
    """Find a <link rel="image_src"> preview image.

    Deliberately does NOT match rel="icon": a favicon is a site logo, not a
    picture of the food, and pages lacking an og:image would otherwise donate
    a 16x16 or 32x32 icon as the recipe's thumbnail.
    """
    match = re.search(
        r'<link[^>]+rel=["\']image_src["\'][^>]+href=["\']([^"\']+)["\']',
        html_text,
        re.IGNORECASE,
    )
    if match:
        return html.unescape(match.group(1))
    return None


# Filenames that are site furniture rather than a photo of the dish.
LOW_VALUE_IMAGE_RE = re.compile(
    r"(favicon|apple-touch-icon|android-chrome|mstile|site[-_]?logo|"
    r"logo[-_.]|[-_]logo|sprite|placeholder|avatar|gravatar|"
    r"[-_]\d{1,2}x\d{1,2}\.)",
    re.IGNORECASE,
)
# An explicit WxH in the filename, e.g. "cropped-Logo-32x32.png".
DIMENSION_HINT_RE = re.compile(r"[-_](\d{2,4})x(\d{2,4})\.[a-z]{3,4}(?:$|[?#])", re.I)
MIN_THUMBNAIL_DIMENSION = 200


def looks_like_photo(url: str | None) -> bool:
    """Cheap URL-only check that a candidate is a real photo, not site chrome.

    Costs no network request. `verify_image_dimensions` does the authoritative
    check by actually measuring the image.
    """
    if not url:
        return False
    path = urlparse(url).path
    if LOW_VALUE_IMAGE_RE.search(path):
        return False
    hint = DIMENSION_HINT_RE.search(path)
    if hint:
        width, height = int(hint.group(1)), int(hint.group(2))
        if max(width, height) < MIN_THUMBNAIL_DIMENSION:
            return False
    if path.lower().endswith(".svg"):
        return False  # vector art is a logo, never a food photo
    return True


def existing_thumbnail_usable(url: str | None) -> bool:
    """Whether a thumbnail already attached to a recipe is worth keeping.

    Only an http(s) URL can be judged. A photo uploaded from a device or
    returned by a generator stores a label like "upload:AB12EF" instead, which
    says nothing about the picture, so those are always kept.
    """
    if not url:
        return False
    if not url.lower().startswith(("http://", "https://")):
        return True
    return looks_like_photo(url)


def verify_image_dimensions(
    url: str, min_dimension: int = MIN_THUMBNAIL_DIMENSION
) -> bool:
    """Download the image and confirm it is large enough to be a thumbnail.

    Returns False on any failure, so an unreachable or unreadable image is
    never proposed. Requires Pillow; if absent, falls back to the URL check.
    """
    if not looks_like_photo(url):
        return False
    try:
        import io

        from PIL import Image

        response = requests.get(url, headers=HTTP_HEADERS, timeout=15, stream=True)
        response.raise_for_status()
        data = response.raw.read(200_000, decode_content=True)
        with Image.open(io.BytesIO(data)) as img:
            return max(img.size) >= min_dimension
    except ImportError:
        return True  # already passed the URL heuristic
    except Exception:
        return False


def source_thumbnail(source_url: str | None) -> str | None:
    """Try to find an image from the recipe source page.

    Candidates that look like site chrome (favicons, logos) are rejected —
    attaching one produces a recipe thumbnail showing the website's logo.
    """
    if not source_url:
        return None

    html_text = _fetch_html(source_url)
    if not html_text:
        return None

    candidate = _extract_meta_content(html_text, ("og:image", "twitter:image"))
    if candidate:
        resolved = urljoin(source_url, candidate)
        if looks_like_photo(resolved):
            return resolved

    candidate = _extract_link_image(html_text)
    if candidate:
        resolved = urljoin(source_url, candidate)
        if looks_like_photo(resolved):
            return resolved

    return None


def web_image_search(query: str) -> str | None:
    """Find a stock photo of the dish via the Pexels API.

    Optional: returns None when PEXELS_API_KEY isn't set, so the thumbnail
    chain simply falls through to the next source. Never raises.

    Pexels is used rather than Google Programmable Search because Google closed
    the Custom Search JSON API to new customers, removed whole-web search for
    new engines (Jan 20, 2026), and retires the API on Jan 1, 2027.

    Returns only the image URL. `web_image_search_detailed` also returns the
    photographer credit, which Pexels asks callers to display where they can.
    """
    result = web_image_search_detailed(query)
    return result["url"] if result else None


def web_image_search_detailed(query: str) -> dict[str, str] | None:
    """Search Pexels and return the image URL plus its attribution.

    Returns a dict with 'url', 'photographer', and 'source_page', or None.
    """
    api_key = os.environ.get("PEXELS_API_KEY")
    safe_query = query.strip()
    if not (api_key and safe_query):
        return None

    try:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            params={
                "query": f"{safe_query} food",
                "per_page": 1,
                "orientation": "landscape",
            },
            headers={**HTTP_HEADERS, "Authorization": api_key},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    for photo in data.get("photos", []):
        src = photo.get("src") or {}
        # Prefer a size close to our 1200px cap; fall back through the rest.
        url = next(
            (
                src[key]
                for key in ("large", "large2x", "medium", "original")
                if src.get(key)
            ),
            None,
        )
        if url:
            return {
                "url": cast(str, url),
                "photographer": photo.get("photographer") or "",
                "source_page": photo.get("url") or "",
            }
    return None


def wikimedia_thumbnail(query: str) -> str | None:
    """Try to find a representative food image on Wikimedia Commons."""
    safe_query = query.strip()
    if not safe_query:
        return None

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": safe_query,
        "gsrlimit": 1,
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json",
    }
    try:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params=params,
            headers=HTTP_HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        imageinfo = page.get("imageinfo") or []
        if imageinfo:
            return cast(str | None, imageinfo[0].get("url"))
    return None


def _search_query_for(recipe: RemoteRecipe) -> str:
    """Build the image-search query for a recipe (name plus a yield hint)."""
    query = recipe.name
    if recipe.notes:
        hint = extract_yield_hint(recipe.notes)
        if hint:
            query = f"{query} {hint}"
    return query


def candidate_thumbnail(
    recipe: RemoteRecipe,
    *,
    fetch_source_image: Callable[[str | None], str | None] = source_thumbnail,
    fetch_web_image: Callable[[str], str | None] = web_image_search,
    fetch_wikimedia_image: Callable[[str], str | None] = wikimedia_thumbnail,
) -> ThumbnailCandidate | None:
    """Find the best free thumbnail candidate for a recipe.

    Priority: an existing thumbnail (only if it passes validation), the
    recipe's own source page, a broad web
    image search (only if configured), a linked YouTube video, then Wikimedia
    Commons. Returns None when no free source yields an image — the caller can
    then fall back to generating one.
    """
    existing = (recipe.image_url or "").strip()
    if existing:
        if existing_thumbnail_usable(existing):
            return ThumbnailCandidate(
                url=existing,
                source="existing",
                confidence=1.0,
                notes="Recipe already has a thumbnail",
            )
        # The current thumbnail is site chrome or a crop too small to use.
        # photo_url holds Paprika's stored copy of that same image, so skip
        # that tier too and go looking for a real replacement. This tier used
        # to return unconditionally at confidence 1.0, which made a bad
        # thumbnail permanently invisible to `find_free_thumbnail`.
    else:
        photo_url = (getattr(recipe, "photo_url", None) or "").strip()
        if photo_url and existing_thumbnail_usable(photo_url):
            return ThumbnailCandidate(
                url=photo_url,
                source="existing_photo_url",
                confidence=0.95,
                notes="Using existing photo_url field",
            )

    source_url = (recipe.source_url or "").strip()
    source_image = fetch_source_image(source_url) if source_url else None
    if source_image:
        return ThumbnailCandidate(
            url=source_image,
            source="source_page",
            confidence=0.9,
            notes="Thumbnail discovered on the recipe source page",
        )

    video_url = extract_youtube_url(
        "\n".join(
            part
            for part in [recipe.source_url, recipe.description, recipe.notes]
            if part
        )
    )
    youtube_image = youtube_thumbnail(video_url)
    if youtube_image:
        return ThumbnailCandidate(
            url=youtube_image,
            source="youtube",
            confidence=0.85,
            notes="Thumbnail derived from a linked YouTube video",
        )

    query = _search_query_for(recipe)

    # Stock photo search. Sits below the recipe's own source page and linked
    # video (which are specific to this recipe) but above Wikimedia, which has
    # thin coverage for anything but well-known dishes.
    web_image = fetch_web_image(query)
    if web_image:
        return ThumbnailCandidate(
            url=web_image,
            source="stock_photo",
            confidence=0.75,
            notes="Stock food photo from Pexels (generic, not this exact recipe)",
        )

    wikimedia_image = fetch_wikimedia_image(query)
    if wikimedia_image:
        return ThumbnailCandidate(
            url=wikimedia_image,
            source="wikimedia",
            confidence=0.7,
            notes="Representative food image from Wikimedia Commons",
        )

    return None


def recipe_text_summary(recipe: RemoteRecipe) -> str:
    """Return a compact text summary for report output."""
    parts = [recipe.name]
    if recipe.source:
        parts.append(f"source={recipe.source}")
    if recipe.servings:
        parts.append(f"servings={recipe.servings}")
    return " | ".join(parts)


def build_recipe_plan(
    recipe: RemoteRecipe,
    *,
    include_thumbnail: bool = True,
    include_description_links: bool = True,
    include_formatting_cleanup: bool = True,
    include_servings_suggestion: bool = True,
) -> RecipePlan:
    """Build a conservative set of updates for a single recipe."""
    findings: list[RecipeFinding] = []
    changes: list[RecipeChange] = []
    updates: dict[str, Any] = {}

    original_ingredients = recipe.ingredients or ""
    original_directions = recipe.directions or ""
    original_description = recipe.description or ""

    cleaned_ingredients = (
        clean_ingredients(original_ingredients) if include_formatting_cleanup else ""
    )
    if (
        include_formatting_cleanup
        and cleaned_ingredients
        and cleaned_ingredients != original_ingredients.strip()
    ):
        updates["ingredients"] = cleaned_ingredients
        changes.append(
            RecipeChange(
                field="ingredients",
                before=original_ingredients,
                after=cleaned_ingredients,
                reason="Normalized ingredient formatting",
            )
        )
        findings.append(
            RecipeFinding(
                code="ingredients_formatting",
                severity="info",
                message="Ingredients were reformatted into a cleaner bullet list.",
            )
        )

    cleaned_directions = (
        clean_instructions(original_directions) if include_formatting_cleanup else ""
    )
    if (
        include_formatting_cleanup
        and cleaned_directions
        and cleaned_directions != original_directions.strip()
    ):
        updates["directions"] = cleaned_directions
        changes.append(
            RecipeChange(
                field="directions",
                before=original_directions,
                after=cleaned_directions,
                reason="Normalized instruction formatting",
            )
        )
        findings.append(
            RecipeFinding(
                code="directions_formatting",
                severity="info",
                message="Instructions were rewritten as a numbered step list.",
            )
        )

    video_url = extract_youtube_url(
        "\n".join(
            part
            for part in [
                recipe.source_url,
                recipe.description,
                recipe.notes,
                recipe.directions,
            ]
            if part
        )
    )
    if include_description_links:
        description_with_links, additions = build_description_with_links(
            original_description, recipe.source_url, video_url
        )
        if additions and description_with_links != original_description.strip():
            updates["description"] = description_with_links
            changes.append(
                RecipeChange(
                    field="description",
                    before=original_description,
                    after=description_with_links,
                    reason="Added source/video links to the description",
                )
            )
            findings.append(
                RecipeFinding(
                    code="description_links",
                    severity="info",
                    message="Added source or video links to the recipe description.",
                )
            )

    thumbnail = candidate_thumbnail(recipe) if include_thumbnail else None
    if include_thumbnail:
        has_existing_thumbnail = bool(
            (recipe.image_url or "").strip()
            or (getattr(recipe, "photo_url", None) or "").strip()
        )
        if thumbnail and not has_existing_thumbnail:
            updates["image_url"] = thumbnail.url
            if getattr(recipe, "photo_url", None) in (None, ""):
                updates["photo_url"] = thumbnail.url
            changes.append(
                RecipeChange(
                    field="image_url",
                    before=recipe.image_url or "",
                    after=thumbnail.url,
                    reason=f"Selected thumbnail from {thumbnail.source}",
                )
            )
            findings.append(
                RecipeFinding(
                    code="thumbnail",
                    severity="info" if thumbnail.confidence >= 0.8 else "warning",
                    message=f"Thumbnail candidate selected from {thumbnail.source}.",
                )
            )

    serving_hint = extract_yield_hint(
        recipe.description or "", recipe.notes or "", recipe.directions or ""
    )
    declared_servings = parse_servings_value(recipe.servings)
    hinted_servings = parse_servings_value(serving_hint)
    if include_servings_suggestion and serving_hint and hinted_servings:
        if declared_servings is None or abs(declared_servings - hinted_servings) > 0.01:
            updates["servings"] = serving_hint
            changes.append(
                RecipeChange(
                    field="servings",
                    before=recipe.servings or "",
                    after=serving_hint,
                    reason="Explicit yield hint found in recipe text",
                )
            )
            findings.append(
                RecipeFinding(
                    code="servings_hint",
                    severity="warning",
                    message=f"Serving size could be updated to {serving_hint} based on recipe text.",
                )
            )

    if not updates:
        status = "leave_unchanged"
    elif any(f.severity == "warning" for f in findings):
        status = "needs_review"
    else:
        status = "safe_to_auto_fix"

    return RecipePlan(
        uid=recipe.uid,
        name=recipe.name,
        updates=updates,
        audit=RecipeAudit(
            uid=recipe.uid,
            name=recipe.name,
            has_thumbnail=bool(
                (recipe.image_url or "").strip()
                or (getattr(recipe, "photo_url", None) or "").strip()
            ),
            status=status,
            findings=findings,
            changes=changes,
            thumbnail=thumbnail,
            serving_suggestion=serving_hint,
        ),
    )

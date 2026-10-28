"""Generate a recipe thumbnail with OpenAI's image model and attach it.

Tier 2 of the thumbnail chain: after `find_free_thumbnail` (free), before the
Higgsfield connector. Each image costs money, so callers confirm with the user
first. The image is generated, normalized to JPEG and attached in one call.
"""

import asyncio
import base64
import os
from typing import Any

import requests
from mcp.types import TextContent

from ..photo import MAX_DIMENSION, attach_photo_bytes, normalize_to_jpeg, stage_photo
from ..utils import find_recipe_by_id, get_remote

OPENAI_IMAGES_URL = "https://api.openai.com/v1/images/generations"
# gpt-image-2 needs a verified OpenAI org; set OPENAI_IMAGE_MODEL to
# gpt-image-1.5 or gpt-image-1 if the account isn't verified.
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_QUALITY = "medium"
QUALITIES = ("low", "medium", "high")
# Generation commonly takes 30-90s. It runs off the event loop, so SSE
# keepalive pings keep the client connection open meanwhile.
GENERATION_TIMEOUT = 240
MAX_DESCRIPTION_CHARS = 300

STYLE = (
    "Overhead three-quarter angle, natural window light, shallow depth of field, "
    "served on a simple ceramic dish, or in fitting glassware for a drink, "
    "against a clean neutral background.\n"
    "Appetizing, realistic, high detail. No text, no logos, no hands, no utensils "
    "in frame."
)


class ImageGenerationError(Exception):
    """OpenAI refused or failed. The message is safe to show the user."""


def build_image_prompt(name: str, description: str | None) -> str:
    """The food-photo prompt for a recipe. Shared with the Higgsfield tier."""
    lines = [f"Professional food photography of {name.strip()}."]
    desc = " ".join((description or "").split())[:MAX_DESCRIPTION_CHARS]
    if desc:
        lines.append(desc)
    lines.append(STYLE)
    return "\n".join(lines)


def generate_image(prompt: str, quality: str) -> tuple[bytes, str]:
    """Call the OpenAI Images API. Returns (image bytes, model used)."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_IMAGE_MODEL") or DEFAULT_MODEL
    try:
        resp = requests.post(
            OPENAI_IMAGES_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "prompt": prompt,
                "size": "1024x1024",
                "quality": quality,
                "n": 1,
            },
            timeout=GENERATION_TIMEOUT,
        )
    except requests.RequestException as e:
        raise ImageGenerationError(
            f"could not reach OpenAI ({type(e).__name__})"
        ) from e
    if resp.status_code != 200:
        try:
            detail = resp.json()["error"]["message"]
        except Exception:
            detail = resp.text[:200]
        raise ImageGenerationError(f"OpenAI returned {resp.status_code}: {detail}")
    try:
        return base64.b64decode(resp.json()["data"][0]["b64_json"]), model
    except Exception as e:
        raise ImageGenerationError("OpenAI's response contained no image") from e


def _text(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=message)]


def _generate_and_attach(
    recipe_id: str, dish_description: str | None, quality: str, replace: bool
) -> list[TextContent]:
    """Blocking body of the tool: look up, generate, normalize, attach."""
    remote = get_remote()
    recipe = find_recipe_by_id(remote, recipe_id)
    if not recipe:
        return _text(f"Error: No recipe found with ID '{recipe_id}'.")

    had_photo = bool(getattr(recipe, "photo", None))
    if had_photo and not replace:
        return _text(
            f"'{recipe.name}' already has a thumbnail, so nothing was generated "
            "(no charge). Pass replace=true only if the user asked to replace it."
        )

    prompt = build_image_prompt(recipe.name, dish_description or recipe.description)
    try:
        raw, model = generate_image(prompt, quality)
    except ImageGenerationError as e:
        return _text(
            f"Image generation failed: {e}. Nothing was attached.\n\n"
            "Fall back to the Higgsfield image tool with this prompt, then attach "
            f"its URL with `set_recipe_photo`:\n\n{prompt}"
        )

    jpeg_bytes = normalize_to_jpeg(raw)
    try:
        result = attach_photo_bytes(remote, recipe, jpeg_bytes, f"generated:{model}")
    except Exception as e:
        # The image is paid for; hold it so a retry doesn't generate again.
        code = stage_photo(jpeg_bytes)
        return _text(
            f"Generated the image, but uploading it to Paprika failed: {e}\n\n"
            f"It is held as upload code {code} for 30 minutes. Retry with "
            f"`set_recipe_photo(id='{recipe_id}', upload_code='{code}')` instead "
            "of generating again."
        )

    status = "replaced" if had_photo else "added"
    return _text(
        f"Generated a thumbnail with {model} ({quality} quality) and {status} it "
        f"on '{recipe.name}' (ID: {recipe_id}).\n"
        f"Stored as: {result['photo_filename']} "
        f"({result['size_kb']} KB JPEG, max {MAX_DIMENSION}px)\n\n"
        f"Prompt used:\n{prompt}"
    )


async def generate_thumbnail_tool(args: dict[str, Any]) -> list[TextContent]:
    """Generate a thumbnail with OpenAI and attach it to the recipe."""
    recipe_id = args.get("id")
    if not recipe_id:
        return _text("Error: 'id' is required.")

    quality = (
        args.get("quality") or os.environ.get("OPENAI_IMAGE_QUALITY") or DEFAULT_QUALITY
    )
    if quality not in QUALITIES:
        return _text(f"Error: 'quality' must be one of {', '.join(QUALITIES)}.")

    if not os.environ.get("OPENAI_API_KEY"):
        return _text(
            "OpenAI image generation is not configured on this server "
            "(OPENAI_API_KEY is unset), so nothing was generated. Fall back to the "
            "Higgsfield image tool, then attach its URL with `set_recipe_photo`."
        )

    return await asyncio.to_thread(
        _generate_and_attach,
        str(recipe_id),
        args.get("dish_description"),
        quality,
        bool(args.get("replace", False)),
    )


TOOL_DEFINITION = {
    "name": "generate_thumbnail",
    "description": (
        "Generate a photorealistic thumbnail for a recipe with OpenAI's image model "
        "(ChatGPT Images, gpt-image-2) and attach it to the recipe in one step. "
        "This is the PREFERRED image generator: use it whenever "
        "`find_free_thumbnail` finds nothing usable, and use Higgsfield only if "
        "this tool reports it is not configured or fails. Costs money (about "
        "$0.06 per image at the default medium quality) and changes real recipe "
        "data: confirm with the user first. Won't replace an existing thumbnail "
        "unless replace=true. Takes 30-90 seconds."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Recipe UID (from search_recipes or read_recipe).",
            },
            "dish_description": {
                "type": "string",
                "description": (
                    "One line describing the finished dish, used in the image "
                    "prompt. Defaults to the recipe's own description."
                ),
            },
            "quality": {
                "type": "string",
                "enum": list(QUALITIES),
                "description": (
                    "Image quality: low (~$0.02), medium (~$0.06, default), "
                    "high (~$0.17)."
                ),
            },
            "replace": {
                "type": "boolean",
                "default": False,
                "description": (
                    "Replace an existing thumbnail. Only when the user asked."
                ),
            },
        },
        "required": ["id"],
    },
}

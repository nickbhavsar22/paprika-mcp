"""Set recipe photo tool - downloads, normalizes, and attaches a thumbnail.

Paprika's photo upload uses the recipe-sync endpoint with a multipart form
that has TWO file parts: `data` (gzipped recipe JSON) and `photo_upload`
(the binary JPEG). The recipe's `photo` field must be a generated
"<UUID>.jpg" filename, NOT base64 — the server stores the binary and
populates `photo_url` (the S3-hosted URL the app uses to render thumbnails).
"""

import hashlib
import io
import uuid as uuid_lib
from typing import Any

import requests
from mcp.types import TextContent

from ..utils import get_remote

MAX_DIMENSION = 1200
JPEG_QUALITY = 85
DOWNLOAD_TIMEOUT = 30
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024  # 25 MB safety cap on the source download


def _download_image(url: str) -> bytes:
    """Download image bytes from URL with a size cap."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=DOWNLOAD_TIMEOUT, stream=True)
    resp.raise_for_status()

    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise ValueError(
                f"Image at {url} exceeds {MAX_DOWNLOAD_BYTES // 1024 // 1024} MB cap"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _normalize_to_jpeg(raw: bytes) -> bytes:
    """Open with Pillow, convert to RGB JPEG, downscale if needed."""
    from PIL import Image  # imported lazily so server still starts without Pillow

    with Image.open(io.BytesIO(raw)) as img:
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if max(img.size) > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return out.getvalue()


async def set_recipe_photo_tool(args: dict[str, Any]) -> list[TextContent]:
    """Download an image, attach it as the recipe's thumbnail, and sync."""
    recipe_id = args["id"]
    image_url = args["image_url"]

    remote = get_remote()

    recipe = None
    for r in remote.recipes:
        if r.uid == recipe_id:
            recipe = r
            break

    if not recipe:
        return [
            TextContent(
                type="text",
                text=f"Error: No recipe found with ID '{recipe_id}'",
            )
        ]

    try:
        raw = _download_image(image_url)
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error downloading image from '{image_url}': {e}",
            )
        ]

    try:
        jpeg_bytes = _normalize_to_jpeg(raw)
    except ImportError:
        return [
            TextContent(
                type="text",
                text=(
                    "Error: Pillow is not installed. "
                    "Run `pip install Pillow` in the paprika-mcp environment."
                ),
            )
        ]
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error normalizing image: {e}",
            )
        ]

    new_size_kb = len(jpeg_bytes) // 1024
    had_photo = bool(getattr(recipe, "photo", None))

    photo_filename = f"{str(uuid_lib.uuid4()).upper()}.jpg"
    recipe.photo = photo_filename
    recipe.photo_hash = hashlib.sha256(jpeg_bytes).hexdigest().upper()
    recipe.image_url = image_url
    # photo_url is server-managed; clear any stale value so the server resets it
    if hasattr(recipe, "photo_url"):
        recipe.photo_url = None
    if hasattr(recipe, "update_hash"):
        recipe.update_hash()

    files = {
        "data": ("data", recipe.as_paprikarecipe()),
        "photo_upload": (photo_filename, jpeg_bytes, "image/jpeg"),
    }

    try:
        # Use Remote's authenticated session via the protected _request helper
        # so we keep the bearer token, retries, and configured user-agent.
        remote._request("post", f"/api/v2/sync/recipe/{recipe.uid}/", files=files)
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error uploading recipe '{recipe.name}': {e}",
            )
        ]

    status = "replaced" if had_photo else "added"
    return [
        TextContent(
            type="text",
            text=(
                f"Successfully {status} photo on recipe '{recipe.name}' "
                f"(ID: {recipe_id})\n"
                f"Source: {image_url}\n"
                f"Stored as: {photo_filename} ({new_size_kb} KB JPEG, "
                f"max {MAX_DIMENSION}px)\n"
                f"Photo hash: {recipe.photo_hash}"
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "set_recipe_photo",
    "description": (
        "Download an image from a URL and attach it as the recipe's thumbnail. "
        "The image is normalized to JPEG (max 1200px, q85) and uploaded to Paprika. "
        "Also updates photo_hash and image_url. "
        "DANGEROUS: requires user confirmation."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Recipe UID to update"},
            "image_url": {
                "type": "string",
                "description": "Public URL of the image to attach as the thumbnail",
            },
        },
        "required": ["id", "image_url"],
    },
}

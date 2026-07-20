"""Set recipe photo tool - attaches a thumbnail from an upload code or URL.

Sources: a browser upload code (from the /upload page — the way to attach a photo
taken on a phone, since a pasted image can't be re-emitted as tool-argument bytes),
or a public image URL. The acquired bytes are normalized to JPEG (max 1200px, q85)
and uploaded to Paprika via the shared photo pipeline.
"""

from typing import Any

from mcp.types import TextContent

from ..photo import (
    MAX_DIMENSION,
    attach_photo_bytes,
    normalize_to_jpeg,
    resolve_image_bytes,
)
from ..utils import get_remote


async def set_recipe_photo_tool(args: dict[str, Any]) -> list[TextContent]:
    """Acquire an image, attach it as the recipe's thumbnail, and sync."""
    recipe_id = args["id"]

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
        raw, source_label = resolve_image_bytes(args)
    except Exception as e:
        return [TextContent(type="text", text=f"Error acquiring image: {e}")]

    try:
        jpeg_bytes = normalize_to_jpeg(raw)
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
        return [TextContent(type="text", text=f"Error normalizing image: {e}")]

    had_photo = bool(getattr(recipe, "photo", None))

    try:
        result = attach_photo_bytes(remote, recipe, jpeg_bytes, source_label)
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
                f"Source: {source_label}\n"
                f"Stored as: {result['photo_filename']} "
                f"({result['size_kb']} KB JPEG, max {MAX_DIMENSION}px)\n"
                f"Photo hash: {result['photo_hash']}"
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "set_recipe_photo",
    "description": (
        "Attach a thumbnail image to a recipe. Provide either `upload_code` (a code "
        "from the /upload page — how to attach a photo taken on a phone) or "
        "`image_url` (a public image URL). The image is normalized to JPEG "
        "(max 1200px, q85) and uploaded to Paprika. "
        "DANGEROUS: requires user confirmation."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Recipe UID to update"},
            "upload_code": {
                "type": "string",
                "description": (
                    "Short code shown after uploading a photo at the /upload page. "
                    "Use this to attach a photo from a phone or computer."
                ),
            },
            "image_url": {
                "type": "string",
                "description": "Public URL of the image to attach as the thumbnail",
            },
        },
        "required": ["id"],
    },
}

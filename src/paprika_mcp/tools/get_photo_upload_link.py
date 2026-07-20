"""Get photo upload link tool - returns the browser upload URL to tap.

A photo attached in a Claude conversation cannot be handed to a tool, so a phone
photo must be uploaded through a browser page (see server_http.py `/upload`). This
tool hands the user the full, ready-to-tap link so they never have to find or paste
the bearer token themselves.
"""

import os
from typing import Any

from mcp.types import TextContent


def _base_url() -> str | None:
    """Public base URL of the hosted server, if known.

    Render injects RENDER_EXTERNAL_URL automatically; PUBLIC_BASE_URL is an
    optional manual override. Returns None when neither is set (e.g. local stdio),
    since the upload page only exists on the hosted HTTP server.
    """
    base = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    return base.rstrip("/") if base else None


async def get_photo_upload_link_tool(args: dict[str, Any]) -> list[TextContent]:
    """Return the tap-to-open photo upload URL."""
    token = os.environ.get("MCP_BEARER_TOKEN")
    base = _base_url()

    if not base or not token:
        return [
            TextContent(
                type="text",
                text=(
                    "Photo uploads are only available on the hosted server "
                    "(the claude.ai connector), not this local session. "
                    "Alternatively, provide a public image URL to set_recipe_photo."
                ),
            )
        ]

    url = f"{base}/upload/{token}"
    return [
        TextContent(
            type="text",
            text=(
                f"Open this link to upload your photo, then tell me to attach it:\n\n"
                f"{url}\n\n"
                "Pick or take a photo, tap Upload, then say something like "
                '"attach it to my Lasagna recipe" and I\'ll grab the photo you just '
                "uploaded. The link stays valid; keep it handy."
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "get_photo_upload_link",
    "description": (
        "Get the browser link the user taps to upload a photo from their phone or "
        "computer. Use this whenever the user wants to add a photo/thumbnail from "
        "their device (a photo pasted into the chat cannot be used directly). After "
        "they upload, call set_recipe_photo (or create_recipe) with just the recipe "
        "and no code — the most recent upload is attached automatically."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
    },
}

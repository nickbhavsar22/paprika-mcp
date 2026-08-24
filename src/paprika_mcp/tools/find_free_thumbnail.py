"""Find a free thumbnail for a recipe - no image generation, no API spend.

This is the first tier of the thumbnail chain. It reuses the discovery pipeline
from `recipe_maintenance` (source page og:image, linked YouTube video, Pexels
stock photo, Wikimedia Commons) and reports the best candidate it finds. Nothing
is attached here — the caller decides whether the candidate is good enough and
then calls `set_recipe_photo`.
"""

from typing import Any

from mcp.types import TextContent

from ..recipe_maintenance import candidate_thumbnail, verify_image_dimensions
from ..utils import find_recipe_by_id, get_remote, normalize_string

# Below this, a candidate is a weak generic match rather than a photo of the
# actual dish, and generating an image is usually the better option.
CONFIDENT_THRESHOLD = 0.75


async def find_free_thumbnail_tool(args: dict[str, Any]) -> list[TextContent]:
    """Look for an existing image of a recipe's dish, free of charge."""
    recipe_id = args.get("id")
    recipe_title = args.get("title")

    if not recipe_id and not recipe_title:
        return [
            TextContent(type="text", text="Error: Must provide either 'id' or 'title'.")
        ]

    remote = get_remote()

    if recipe_id:
        recipe = find_recipe_by_id(remote, str(recipe_id))
        if not recipe:
            return [
                TextContent(
                    type="text",
                    text=f"Error: No recipe found with ID '{recipe_id}'.",
                )
            ]
    else:
        normalized = normalize_string(str(recipe_title))
        recipe = None
        for r in remote.recipes:
            if normalize_string(r.name) == normalized:
                recipe = r
                break
        if not recipe:
            return [
                TextContent(
                    type="text",
                    text=f"Error: No recipe found with title '{recipe_title}'.",
                )
            ]

    candidate = candidate_thumbnail(recipe)

    # Measure the image before recommending it. A source page can advertise a
    # tiny logo as its preview image, which would become the recipe thumbnail.
    # If the page's own image fails, retry without that tier so we still fall
    # through to a stock photo rather than returning nothing.
    if candidate and candidate.source == "source_page":
        if not verify_image_dimensions(candidate.url):
            candidate = candidate_thumbnail(
                recipe, fetch_source_image=lambda _url: None
            )

    if candidate is None:
        return [
            TextContent(
                type="text",
                text=(
                    f"No free thumbnail found for '{recipe.name}'.\n\n"
                    "Nothing usable on the recipe's source page, linked video, "
                    "Pexels, or Wikimedia Commons. Next step: generate an image "
                    "(see the `set_recipe_thumbnail` prompt for the chain)."
                ),
            )
        ]

    if candidate.source in ("existing", "existing_photo_url"):
        return [
            TextContent(
                type="text",
                text=(
                    f"'{recipe.name}' already has a thumbnail — nothing to do.\n\n"
                    f"**Current image:** {candidate.url}\n"
                    "Only replace it if the user explicitly asked for a new one."
                ),
            )
        ]

    # Getting here with a thumbnail still on the recipe means it failed
    # validation, so say plainly that attaching would replace it.
    current = (recipe.image_url or "").strip()
    replacing = ""
    if current:
        replacing = (
            f"\n\n**Replaces the current thumbnail**, which failed "
            f"validation (site chrome, or too small to use):\n{current}"
        )

    confident = candidate.confidence >= CONFIDENT_THRESHOLD
    verdict = (
        "Good candidate — attach it with `set_recipe_photo`."
        if confident
        else (
            "Weak candidate. Show the user the URL and ask, or generate an image "
            "instead (see the `set_recipe_thumbnail` prompt)."
        )
    )

    return [
        TextContent(
            type="text",
            text=(
                f"Free thumbnail candidate for '{recipe.name}':\n\n"
                f"**URL:** {candidate.url}\n"
                f"**Source:** {candidate.source}\n"
                f"**Confidence:** {candidate.confidence:.2f}\n"
                f"**Notes:** {candidate.notes}"
                f"{replacing}\n\n"
                f"{verdict}"
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "find_free_thumbnail",
    "description": (
        "Find an existing, free image to use as a recipe's thumbnail — ALWAYS try "
        "this before generating one, since generation costs money. Searches the "
        "recipe's own source page, any linked YouTube video, Pexels stock photos, "
        "and Wikimedia Commons, and returns the best candidate URL with a "
        "confidence score. It does NOT attach anything: pass the returned URL to "
        "`set_recipe_photo` if it looks right. Also re-checks a thumbnail the recipe "
        "already has, and proposes a replacement when that one is a logo or too "
        "small to use. If nothing is found, fall back to "
        "image generation (see the `set_recipe_thumbnail` prompt for the full chain)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Recipe UID (from search_recipes or read_recipe).",
            },
            "title": {
                "type": "string",
                "description": "Exact recipe title (alternative to id).",
            },
        },
        "required": [],
    },
}

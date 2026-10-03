"""Set recipe rating tool - sets the 0-5 star rating on a recipe."""

from typing import Any

from mcp.types import TextContent

from ..utils import find_recipe_by_id, get_remote


def parse_rating(value: Any) -> int | None:
    """Return the rating as an int 0-5, or None if it is not one.

    Accepts 4, 4.0 and "4" (clients vary in how they send numbers); rejects
    booleans, fractions like 3.5, and anything outside 0-5.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not value.lstrip("-").isdigit():
            return None
        value = int(value)
    if isinstance(value, float):
        if not value.is_integer():
            return None
        value = int(value)
    if isinstance(value, int) and 0 <= value <= 5:
        return value
    return None


def _stars(rating: int) -> str:
    return f"{rating}/5" if rating else "unrated"


async def set_recipe_rating_tool(args: dict[str, Any]) -> list[TextContent]:
    """Set the star rating on an existing recipe."""
    recipe_id = args.get("id")
    if not recipe_id:
        return [TextContent(type="text", text="Error: 'id' is required.")]

    rating = parse_rating(args.get("rating"))
    if rating is None:
        return [
            TextContent(
                type="text",
                text=(
                    "Error: 'rating' must be a whole number from 0 to 5 "
                    "(0 clears the rating)."
                ),
            )
        ]

    remote = get_remote()
    recipe = find_recipe_by_id(remote, str(recipe_id))
    if not recipe:
        return [
            TextContent(
                type="text",
                text=f"Error: No recipe found with ID '{recipe_id}'.",
            )
        ]

    old_rating = recipe.rating or 0
    if old_rating == rating:
        return [
            TextContent(
                type="text",
                text=f"No change - '{recipe.name}' is already {_stars(rating)}.",
            )
        ]

    recipe.rating = rating
    try:
        remote.upload_recipe(recipe)
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error updating rating on '{recipe.name}': {e}",
            )
        ]

    return [
        TextContent(
            type="text",
            text=(
                f"Rating updated on '{recipe.name}' (ID: {recipe_id}).\n\n"
                f"**Before:** {_stars(old_rating)}\n"
                f"**After:** {_stars(rating)}"
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "set_recipe_rating",
    "description": (
        "Set the star rating (0-5) on an existing recipe. Use 0 to clear the "
        "rating. Changes real recipe data: confirm with the user first."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Recipe UID (from search_recipes or read_recipe).",
            },
            "rating": {
                "type": "integer",
                "minimum": 0,
                "maximum": 5,
                "description": "Star rating from 1 to 5, or 0 to clear it.",
            },
        },
        "required": ["id", "rating"],
    },
}

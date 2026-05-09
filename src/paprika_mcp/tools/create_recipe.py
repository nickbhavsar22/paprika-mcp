"""Create recipe tool - adds a new recipe to Paprika."""

from typing import Any

from mcp.types import TextContent
from paprika_recipes.remote import RemoteRecipe

from ..utils import get_categories, get_remote


async def create_recipe_tool(args: dict[str, Any]) -> list[TextContent]:
    """Create a new recipe in Paprika."""
    name = args.get("name")
    if not name:
        return [TextContent(type="text", text="Error: 'name' is required.")]

    remote = get_remote()
    token = remote.bearer_token

    # Resolve category names to UIDs
    category_names = args.get("categories", [])
    category_uids: list[str] = []
    unresolved: list[str] = []
    if category_names:
        cats = get_categories(token)
        for cat_name in category_names:
            uid = cats["name_to_uid"].get(cat_name.lower())
            if uid:
                category_uids.append(uid)
            else:
                unresolved.append(cat_name)

    # Build recipe
    recipe = RemoteRecipe(
        name=name,
        ingredients=args.get("ingredients", ""),
        directions=args.get("directions", ""),
        description=args.get("description", ""),
        notes=args.get("notes", ""),
        servings=args.get("servings", ""),
        prep_time=args.get("prep_time", ""),
        cook_time=args.get("cook_time", ""),
        total_time=args.get("total_time", ""),
        difficulty=args.get("difficulty", ""),
        source=args.get("source", ""),
        source_url=args.get("source_url", ""),
        categories=category_uids,
        rating=args.get("rating", 0),
        on_favorites=args.get("on_favorites", False),
    )

    try:
        remote.upload_recipe(recipe)
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error creating recipe: {e}",
            )
        ]

    # Build response
    lines = [
        "Recipe created successfully.\n",
        f"**Name:** {recipe.name}",
        f"**Recipe ID:** {recipe.uid}",
    ]
    if category_uids:
        cats_data = get_categories(token)
        resolved_names = [
            cats_data["uid_to_name"].get(uid, uid) for uid in category_uids
        ]
        lines.append(f"**Categories:** {', '.join(resolved_names)}")
    if unresolved:
        lines.append(
            f"\nWarning: Unrecognized categories (skipped): {', '.join(unresolved)}"
        )
    lines.append(
        "\nUse `set_recipe_photo` with the Recipe ID above to add a thumbnail image."
    )

    return [TextContent(type="text", text="\n".join(lines))]


TOOL_DEFINITION = {
    "name": "create_recipe",
    "description": (
        "Create a new recipe in Paprika. "
        "This is a DANGEROUS operation that requires user confirmation. "
        "Only 'name' is required; all other fields are optional. "
        "Categories should be provided as an array of category names "
        "(use list_categories to see available categories). "
        "After creating, use set_recipe_photo to attach a thumbnail image."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Recipe title (e.g., 'Classic Gin and Tonic').",
            },
            "ingredients": {
                "type": "string",
                "description": (
                    "Ingredients list, one per line "
                    "(e.g., '2 oz gin\\n4-6 oz tonic water\\n1 lime')."
                ),
            },
            "directions": {
                "type": "string",
                "description": (
                    "Cooking/preparation instructions, one step per line "
                    "(e.g., '1. Fill glass with ice\\n2. Pour gin over ice')."
                ),
            },
            "description": {
                "type": "string",
                "description": "Short description or summary of the recipe.",
            },
            "notes": {
                "type": "string",
                "description": "Additional notes, tips, or variations.",
            },
            "servings": {
                "type": "string",
                "description": "Number of servings (e.g., '4', '1 cocktail').",
            },
            "prep_time": {
                "type": "string",
                "description": "Preparation time (e.g., '15 min').",
            },
            "cook_time": {
                "type": "string",
                "description": "Cooking time (e.g., '30 min').",
            },
            "total_time": {
                "type": "string",
                "description": "Total time (e.g., '45 min').",
            },
            "difficulty": {
                "type": "string",
                "description": "Difficulty level (e.g., 'Easy', 'Medium', 'Hard').",
            },
            "source": {
                "type": "string",
                "description": "Where the recipe came from (e.g., 'Bon Appetit').",
            },
            "source_url": {
                "type": "string",
                "description": "URL where the recipe was found.",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Category names to assign (e.g., ['Cocktails', 'Drinks']). "
                    "Use list_categories to see available categories. "
                    "Unrecognized names are silently skipped with a warning."
                ),
            },
            "rating": {
                "type": "integer",
                "minimum": 0,
                "maximum": 5,
                "description": "Star rating from 0 to 5.",
            },
            "on_favorites": {
                "type": "boolean",
                "description": "Whether to add the recipe to favorites (default: false).",
                "default": False,
            },
        },
        "required": ["name"],
    },
}

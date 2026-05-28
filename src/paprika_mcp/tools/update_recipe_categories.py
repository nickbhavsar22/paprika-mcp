"""Update recipe categories tool - replaces the category list on a recipe."""

from typing import Any

from mcp.types import TextContent

from ..utils import get_categories, get_remote, translate_category_uids


async def update_recipe_categories_tool(args: dict[str, Any]) -> list[TextContent]:
    """Replace the categories on an existing recipe."""
    recipe_id = args.get("id")
    category_names = args.get("categories")

    if not recipe_id:
        return [TextContent(type="text", text="Error: 'id' is required.")]
    if category_names is None:
        return [TextContent(type="text", text="Error: 'categories' is required.")]

    remote = get_remote()
    token = remote.bearer_token

    recipe = None
    for r in remote.recipes:
        if r.uid == recipe_id:
            recipe = r
            break

    if not recipe:
        return [
            TextContent(
                type="text",
                text=f"Error: No recipe found with ID '{recipe_id}'.",
            )
        ]

    # Capture old categories for display
    old_names = translate_category_uids(recipe.categories or [], token)

    # Resolve new category names to UIDs
    cats = get_categories(token)
    new_uids: list[str] = []
    unresolved: list[str] = []
    for name in category_names:
        uid = cats["name_to_uid"].get(name.lower())
        if uid:
            new_uids.append(uid)
        else:
            unresolved.append(name)

    recipe.categories = new_uids

    try:
        remote.upload_recipe(recipe)
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error updating categories on '{recipe.name}': {e}",
            )
        ]

    new_names = translate_category_uids(new_uids, token)
    lines = [
        f"Categories updated on '{recipe.name}'.\n",
        f"**Before:** {old_names or '(none)'}",
        f"**After:** {new_names or '(none)'}",
    ]
    if unresolved:
        lines.append(
            f"\nWarning: Unrecognized categories (skipped): {', '.join(unresolved)}"
        )

    return [TextContent(type="text", text="\n".join(lines))]


TOOL_DEFINITION = {
    "name": "update_recipe_categories",
    "description": (
        "Replace the categories on an existing recipe. "
        "Accepts category names (use list_categories to see available categories). "
        "Pass an empty array to remove all categories. "
        "DANGEROUS: requires user confirmation."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Recipe UID to update (from search_recipes or read_recipe).",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "New category names to assign (replaces the entire list). "
                    "Use list_categories to see available categories. "
                    "Pass [] to remove all categories."
                ),
            },
        },
        "required": ["id", "categories"],
    },
}

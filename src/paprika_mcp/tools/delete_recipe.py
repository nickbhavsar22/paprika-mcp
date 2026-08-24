"""Delete recipe tool - moves a recipe to the trash."""

from typing import Any

from mcp.types import TextContent

from ..utils import find_recipe_by_id, get_remote


async def delete_recipe_tool(args: dict[str, Any]) -> list[TextContent]:
    """Delete a recipe by moving it to the trash."""
    recipe_id = args.get("id")
    if not recipe_id:
        return [TextContent(type="text", text="Error: 'id' is required.")]

    remote = get_remote()

    recipe = find_recipe_by_id(remote, str(recipe_id))

    if not recipe:
        return [
            TextContent(
                type="text",
                text=f"Error: No recipe found with ID '{recipe_id}'.",
            )
        ]

    recipe_name = recipe.name
    recipe.in_trash = True

    try:
        remote.upload_recipe(recipe)
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error deleting recipe '{recipe_name}': {e}",
            )
        ]

    return [
        TextContent(
            type="text",
            text=f"Recipe '{recipe_name}' moved to trash successfully.",
        )
    ]


TOOL_DEFINITION = {
    "name": "delete_recipe",
    "description": (
        "Delete a recipe by moving it to the trash in Paprika. "
        "DANGEROUS: requires user confirmation. "
        "The recipe can be recovered from the trash in the Paprika app."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": "Recipe UID to delete (from search_recipes or read_recipe).",
            },
        },
        "required": ["id"],
    },
}

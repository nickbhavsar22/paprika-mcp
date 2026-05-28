"""Delete category tool - removes a recipe category."""

from typing import Any

from mcp.types import TextContent

from ..utils import get_categories, get_remote, save_category


async def delete_category_tool(args: dict[str, Any]) -> list[TextContent]:
    """Delete a recipe category from Paprika."""
    name = args.get("name")
    if not name:
        return [TextContent(type="text", text="Error: 'name' is required.")]

    remote = get_remote()
    token = remote.bearer_token

    cats = get_categories(token)
    cat_uid = cats["name_to_uid"].get(name.lower())
    if not cat_uid:
        available = sorted(cats["name_to_uid"].keys())
        return [
            TextContent(
                type="text",
                text=(
                    f"Error: Category '{name}' not found.\n"
                    f"Available categories: {', '.join(available)}"
                ),
            )
        ]

    cat_data = cats["by_uid"].get(cat_uid, {}).copy()
    if not cat_data:
        cat_data = {"uid": cat_uid, "name": name}
    cat_data["deleted"] = True

    result = save_category(token, cat_data)
    if not result["success"]:
        return [
            TextContent(
                type="text",
                text=f"Error deleting category: {result['error']}",
            )
        ]

    return [
        TextContent(
            type="text",
            text=f"Category '{name}' deleted successfully.",
        )
    ]


TOOL_DEFINITION = {
    "name": "delete_category",
    "description": (
        "Delete a recipe category from Paprika. "
        "Recipes in this category will not be deleted, "
        "but they will lose this category assignment. "
        "DANGEROUS: requires user confirmation."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Name of the category to delete. "
                    "Use list_categories to see available categories."
                ),
            },
        },
        "required": ["name"],
    },
}

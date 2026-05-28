"""Create category tool - adds a new recipe category."""

import uuid
from typing import Any

from mcp.types import TextContent

from ..utils import get_categories, get_remote, save_category


async def create_category_tool(args: dict[str, Any]) -> list[TextContent]:
    """Create a new recipe category in Paprika."""
    name = args.get("name")
    if not name:
        return [TextContent(type="text", text="Error: 'name' is required.")]

    parent_name = args.get("parent")

    remote = get_remote()
    token = remote.bearer_token

    # Check if category already exists
    cats = get_categories(token)
    if name.lower() in cats["name_to_uid"]:
        return [
            TextContent(
                type="text",
                text=f"Error: Category '{name}' already exists.",
            )
        ]

    # Resolve parent if provided
    parent_uid = None
    if parent_name:
        parent_uid = cats["name_to_uid"].get(parent_name.lower())
        if not parent_uid:
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Error: Parent category '{parent_name}' not found. "
                        "Use list_categories to see available categories."
                    ),
                )
            ]

    cat_uid = str(uuid.uuid4()).upper()
    cat_data = {
        "uid": cat_uid,
        "name": name,
        "parent_uid": parent_uid,
        "order_flag": 0,
    }

    result = save_category(token, cat_data)
    if not result["success"]:
        return [
            TextContent(
                type="text",
                text=f"Error creating category: {result['error']}",
            )
        ]

    lines = [
        f"Category '{name}' created successfully.\n",
        f"**Category ID:** {cat_uid}",
    ]
    if parent_name:
        lines.append(f"**Parent:** {parent_name}")

    return [TextContent(type="text", text="\n".join(lines))]


TOOL_DEFINITION = {
    "name": "create_category",
    "description": (
        "Create a new recipe category in Paprika. "
        "Optionally specify a parent category to create a subcategory."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name for the new category (e.g., 'Cocktails', 'Quick Meals').",
            },
            "parent": {
                "type": "string",
                "description": (
                    "Parent category name to nest under (optional). "
                    "Use list_categories to see available categories."
                ),
            },
        },
        "required": ["name"],
    },
}

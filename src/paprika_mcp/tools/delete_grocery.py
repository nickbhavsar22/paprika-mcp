"""Delete grocery tool - removes a grocery item from the list."""

from typing import Any

from mcp.types import TextContent

from ..utils import get_groceries, get_remote, save_grocery


async def delete_grocery_tool(args: dict[str, Any]) -> list[TextContent]:
    """Delete a grocery item by marking it as deleted."""
    item_id = args.get("item_id")
    if not item_id:
        return [TextContent(type="text", text="Error: 'item_id' is required.")]

    remote = get_remote()
    token = remote.bearer_token

    # Find the existing item
    all_items = get_groceries(token)
    existing = None
    for item in all_items:
        if item.get("uid") == item_id:
            existing = item
            break

    if not existing:
        return [
            TextContent(
                type="text",
                text=f"Error: No grocery item found with ID '{item_id}'.",
            )
        ]

    item_name = existing.get("name", "Unknown")

    # Soft-delete
    existing["deleted"] = True
    result = save_grocery(token, existing)
    if not result["success"]:
        return [
            TextContent(
                type="text",
                text=f"Error deleting grocery item: {result['error']}",
            )
        ]

    return [
        TextContent(
            type="text",
            text=f"Grocery item '{item_name}' deleted successfully.",
        )
    ]


TOOL_DEFINITION = {
    "name": "delete_grocery",
    "description": (
        "Delete a grocery item from the list. "
        "Requires the item_id from list_groceries output. "
        "DANGEROUS: requires user confirmation."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "description": "UID of the grocery item to delete (from list_groceries).",
            },
        },
        "required": ["item_id"],
    },
}

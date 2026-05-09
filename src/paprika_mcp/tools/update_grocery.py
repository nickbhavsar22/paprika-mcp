"""Update grocery tool - modifies a grocery item or marks it purchased."""

from typing import Any

from mcp.types import TextContent

from ..utils import (
    get_groceries,
    get_remote,
    resolve_aisle_uid,
    save_grocery,
)


async def update_grocery_tool(args: dict[str, Any]) -> list[TextContent]:
    """Update an existing grocery item."""
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

    # Apply updates
    updated_fields = []

    if "name" in args:
        existing["name"] = args["name"]
        existing["ingredient"] = args["name"]
        updated_fields.append(f"name -> {args['name']}")

    if "quantity" in args:
        existing["quantity"] = args["quantity"]
        updated_fields.append(f"quantity -> {args['quantity']}")

    if "aisle" in args:
        existing["aisle"] = args["aisle"]
        existing["aisle_uid"] = resolve_aisle_uid(args["aisle"], token)
        updated_fields.append(f"aisle -> {args['aisle']}")

    if "purchased" in args:
        existing["purchased"] = args["purchased"]
        status = "purchased" if args["purchased"] else "unpurchased"
        updated_fields.append(f"marked {status}")

    if "instruction" in args:
        existing["instruction"] = args["instruction"]
        updated_fields.append(f"instruction -> {args['instruction']}")

    if not updated_fields:
        return [
            TextContent(
                type="text",
                text="Error: No fields to update. Provide at least one of: "
                "name, quantity, aisle, purchased, instruction.",
            )
        ]

    result = save_grocery(token, existing)
    if not result["success"]:
        return [
            TextContent(
                type="text",
                text=f"Error updating grocery item: {result['error']}",
            )
        ]

    return [
        TextContent(
            type="text",
            text=(
                f"Grocery item updated successfully.\n\n"
                f"**Item:** {existing.get('name', 'Unknown')}\n"
                f"**Changes:** {'; '.join(updated_fields)}\n"
                f"**Item ID:** {item_id}"
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "update_grocery",
    "description": (
        "Update a grocery item - change its name, quantity, aisle, instructions, "
        "or mark it as purchased/unpurchased. "
        "Requires the item_id from list_groceries output.\n\n"
        "Common use: mark an item as purchased with purchased=true."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "description": "UID of the grocery item to update (from list_groceries).",
            },
            "name": {
                "type": "string",
                "description": "New name for the item.",
            },
            "quantity": {
                "type": "string",
                "description": "New quantity (e.g., '2 lbs', '1 gallon').",
            },
            "aisle": {
                "type": "string",
                "description": "New aisle name.",
            },
            "purchased": {
                "type": "boolean",
                "description": "Mark as purchased (true) or unpurchased (false).",
            },
            "instruction": {
                "type": "string",
                "description": "New instructions or notes.",
            },
        },
        "required": ["item_id"],
    },
}

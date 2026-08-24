"""Add grocery tool - adds an item to a Paprika grocery list."""

import uuid
from typing import Any

from mcp.types import TextContent

from ..utils import (
    aisle_names,
    find_recipe_by_id,
    get_grocery_lists,
    get_remote,
    resolve_aisle_uid,
    resolve_grocery_list,
    save_grocery,
)


async def add_grocery_tool(args: dict[str, Any]) -> list[TextContent]:
    """Add a new item to a Paprika grocery list."""
    name = args.get("name")
    if not name:
        return [TextContent(type="text", text="Error: 'name' is required.")]

    quantity = args.get("quantity", "")
    aisle = args.get("aisle", "")
    list_name = args.get("list")
    recipe_id = args.get("recipe_id")
    instruction = args.get("instruction", "")

    remote = get_remote()
    token = remote.bearer_token

    # Resolve grocery list
    target_list = resolve_grocery_list(list_name, token)
    if not target_list:
        all_lists = get_grocery_lists(token)
        names = [gl.get("name", "?") for gl in all_lists]
        return [
            TextContent(
                type="text",
                text=(
                    f"Error: Grocery list '{list_name}' not found.\n"
                    f"Available lists: {', '.join(names)}"
                ),
            )
        ]

    # Resolve aisle UID. An unrecognized name still saves, but Paprika won't
    # file the item under that aisle — say so rather than failing silently.
    aisle_uid = resolve_aisle_uid(aisle, token) if aisle else None
    aisle_warning = None
    if aisle and aisle_uid is None:
        known = ", ".join(n for n in aisle_names(token) if n)
        aisle_warning = (
            f"Aisle '{aisle}' does not match an existing Paprika aisle, so the item "
            f"was not filed under one."
            + (f" Available aisles: {known}" if known else "")
        )

    # Resolve the linked recipe's name. Paprika displays the `recipe` field on
    # the item; `recipe_uid` alone shows nothing.
    recipe_name = None
    if recipe_id:
        linked = find_recipe_by_id(remote, str(recipe_id))
        if linked is None:
            return [
                TextContent(
                    type="text",
                    text=f"Error: No recipe found with ID '{recipe_id}'.",
                )
            ]
        recipe_name = linked.name

    # Build grocery item
    item_uid = str(uuid.uuid4()).upper()
    item_data: dict[str, Any] = {
        "uid": item_uid,
        "name": name,
        "ingredient": name,
        "quantity": quantity,
        "aisle": aisle,
        "aisle_uid": aisle_uid or "",
        "list_uid": target_list["uid"],
        "recipe_uid": recipe_id,
        "recipe": recipe_name,
        "purchased": False,
        "order_flag": 0,
        "instruction": instruction,
        "separate": False,
    }

    result = save_grocery(token, item_data)
    if not result["success"]:
        return [
            TextContent(
                type="text",
                text=f"Error adding grocery item: {result['error']}",
            )
        ]

    list_display = target_list.get("name", "Unknown")
    return [
        TextContent(
            type="text",
            text=(
                f"Grocery item added successfully.\n\n"
                f"**Name:** {name}\n"
                f"**List:** {list_display}\n"
                + (f"**Quantity:** {quantity}\n" if quantity else "")
                + (f"**Aisle:** {aisle}\n" if aisle else "")
                + (f"**Recipe:** {recipe_name}\n" if recipe_name else "")
                + (f"**Note:** {instruction}\n" if instruction else "")
                + f"**Item ID:** {item_uid}"
                + (f"\n\nWarning: {aisle_warning}" if aisle_warning else "")
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "add_grocery",
    "description": (
        "Add an item to a Paprika grocery list. "
        "If no list is specified, the item is added to the default grocery list. "
        "You can specify a quantity, aisle, and optional instructions."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the grocery item (e.g., 'Whole milk', 'Chicken breast').",
            },
            "quantity": {
                "type": "string",
                "description": "Amount to buy (e.g., '2 lbs', '1 gallon', '3').",
            },
            "aisle": {
                "type": "string",
                "description": (
                    "Aisle name (e.g., 'Produce', 'Dairy', 'Frozen Foods'). "
                    "Must match an existing aisle name in Paprika."
                ),
            },
            "list": {
                "type": "string",
                "description": (
                    "Which grocery list to add to "
                    "(e.g., 'Costco', 'Whole Foods', 'HEB'). "
                    "If not specified, uses the default list."
                ),
            },
            "recipe_id": {
                "type": "string",
                "description": "UID of a recipe to link this item to.",
            },
            "instruction": {
                "type": "string",
                "description": "Additional instructions or notes for this item.",
            },
        },
        "required": ["name"],
    },
}

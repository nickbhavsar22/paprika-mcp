"""Update grocery tool - modifies a grocery item or marks it purchased."""

from typing import Any

from mcp.types import TextContent

from ..utils import (
    aisle_names,
    find_recipe_by_id,
    get_groceries,
    get_grocery_lists,
    get_remote,
    resolve_aisle_uid,
    resolve_grocery_list,
    save_grocery,
)


def _as_bool(value: Any) -> bool | None:
    """Coerce a JSON-ish truthy value to bool; None if unrecognizable.

    Clients occasionally send "true"/"false" strings or 0/1 for a boolean
    field, which would otherwise be stored verbatim and read back as truthy.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "yes", "1"):
            return True
        if lowered in ("false", "no", "0"):
            return False
    return None


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
    warnings = []

    if "name" in args:
        existing["name"] = args["name"]
        existing["ingredient"] = args["name"]
        updated_fields.append(f"name -> {args['name']}")

    if "quantity" in args:
        existing["quantity"] = args["quantity"]
        updated_fields.append(f"quantity -> {args['quantity']}")

    if "aisle" in args:
        aisle = args["aisle"]
        existing["aisle"] = aisle
        aisle_uid = resolve_aisle_uid(aisle, token) if aisle else None
        existing["aisle_uid"] = aisle_uid or ""
        updated_fields.append(f"aisle -> {aisle}")
        if aisle and aisle_uid is None:
            known = ", ".join(n for n in aisle_names(token) if n)
            warnings.append(
                f"Aisle '{aisle}' does not match an existing Paprika aisle."
                + (f" Available aisles: {known}" if known else "")
            )

    if "list" in args:
        target_list = resolve_grocery_list(args["list"], token)
        if not target_list:
            names = [gl.get("name", "?") for gl in get_grocery_lists(token)]
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Error: Grocery list '{args['list']}' not found.\n"
                        f"Available lists: {', '.join(names)}"
                    ),
                )
            ]
        existing["list_uid"] = target_list["uid"]
        updated_fields.append(f"list -> {target_list.get('name', 'Unknown')}")

    if "recipe_id" in args:
        recipe_id = args["recipe_id"]
        if recipe_id:
            linked = find_recipe_by_id(remote, str(recipe_id))
            if linked is None:
                return [
                    TextContent(
                        type="text",
                        text=f"Error: No recipe found with ID '{recipe_id}'.",
                    )
                ]
            existing["recipe_uid"] = recipe_id
            existing["recipe"] = linked.name
            updated_fields.append(f"recipe -> {linked.name}")
        else:
            existing["recipe_uid"] = None
            existing["recipe"] = None
            updated_fields.append("recipe link removed")

    if "purchased" in args:
        coerced = _as_bool(args["purchased"])
        if coerced is None:
            return [
                TextContent(
                    type="text",
                    text=(
                        f"Error: 'purchased' must be true or false "
                        f"(got {args['purchased']!r})."
                    ),
                )
            ]
        existing["purchased"] = coerced
        updated_fields.append(f"marked {'purchased' if coerced else 'unpurchased'}")

    if "instruction" in args:
        existing["instruction"] = args["instruction"]
        updated_fields.append(f"instruction -> {args['instruction']}")

    if not updated_fields:
        return [
            TextContent(
                type="text",
                text="Error: No fields to update. Provide at least one of: "
                "name, quantity, aisle, list, recipe_id, purchased, instruction.",
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
                + ("\n\nWarning: " + " ".join(warnings) if warnings else "")
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "update_grocery",
    "description": (
        "Update a grocery item - change its name, quantity, aisle, instructions, "
        "linked recipe, which list it belongs to, or mark it purchased/unpurchased. "
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
            "list": {
                "type": "string",
                "description": (
                    "Move the item to a different grocery list, by name "
                    "(e.g. 'Costco', 'HEB'). Use list_grocery_lists to see names."
                ),
            },
            "recipe_id": {
                "type": "string",
                "description": (
                    "Link the item to a recipe by UID (the recipe name is stored "
                    "so Paprika displays it). Pass an empty string to unlink."
                ),
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

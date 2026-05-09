"""List groceries tool - shows grocery list items."""

from typing import Any

from mcp.types import TextContent

from ..utils import get_groceries, get_grocery_lists, get_remote, resolve_grocery_list


async def list_groceries_tool(args: dict[str, Any]) -> list[TextContent]:
    """List grocery items, optionally filtered by list, aisle, or purchased status."""
    list_name = args.get("list")
    aisle_filter = args.get("aisle")
    show_purchased = args.get("show_purchased", False)

    remote = get_remote()
    token = remote.bearer_token

    # Resolve which grocery list to show
    target_list = None
    if list_name:
        target_list = resolve_grocery_list(list_name, token)
        if not target_list:
            # List available lists
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

    all_items = get_groceries(token)

    if not all_items:
        return [TextContent(type="text", text="No grocery items found.")]

    # Filter by list
    if target_list:
        all_items = [i for i in all_items if i.get("list_uid") == target_list["uid"]]

    # Filter by purchased status
    if not show_purchased:
        all_items = [i for i in all_items if not i.get("purchased")]

    # Filter by aisle
    if aisle_filter:
        aisle_lower = aisle_filter.lower()
        all_items = [
            i for i in all_items if aisle_lower in i.get("aisle", "").lower()
        ]

    if not all_items:
        filters = []
        if list_name:
            filters.append(f"list '{list_name}'")
        if aisle_filter:
            filters.append(f"aisle '{aisle_filter}'")
        if not show_purchased:
            filters.append("unpurchased only")
        desc = f" ({', '.join(filters)})" if filters else ""
        return [
            TextContent(type="text", text=f"No grocery items found{desc}.")
        ]

    # Group by list, then by aisle
    by_list: dict[str, list[dict[str, Any]]] = {}
    for item in all_items:
        lid = item.get("list_uid", "")
        by_list.setdefault(lid, []).append(item)

    # Build list name lookup
    grocery_lists = get_grocery_lists(token)
    list_names = {gl["uid"]: gl.get("name", "Unknown") for gl in grocery_lists}

    output_lines = [f"Found {len(all_items)} grocery items\n"]

    for list_uid in sorted(by_list.keys(), key=lambda u: list_names.get(u, "")):
        lname = list_names.get(list_uid, "Unknown List")
        items = by_list[list_uid]
        output_lines.append(f"## {lname}")

        # Group by aisle within this list
        by_aisle: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            aisle = item.get("aisle", "") or "No Aisle"
            by_aisle.setdefault(aisle, []).append(item)

        for aisle_name in sorted(by_aisle.keys()):
            if aisle_name != "No Aisle":
                output_lines.append(f"### {aisle_name}")
            for item in by_aisle[aisle_name]:
                name = item.get("name", "Unnamed")
                qty = item.get("quantity", "")
                purchased = item.get("purchased", False)
                recipe = item.get("recipe")
                instruction = item.get("instruction", "")
                uid = item.get("uid", "")

                check = "[x]" if purchased else "[ ]"
                parts = [f"- {check} {name}"]
                if qty:
                    parts[0] += f" ({qty})"
                if instruction:
                    parts.append(f"  Note: {instruction}")
                if recipe:
                    parts.append(f"  Recipe: {recipe}")
                parts.append(f"  [item_id: {uid}]")
                output_lines.append("\n".join(parts))

        output_lines.append("")

    return [TextContent(type="text", text="\n".join(output_lines))]


TOOL_DEFINITION = {
    "name": "list_groceries",
    "description": (
        "List grocery items from Paprika. "
        "By default shows only unpurchased items across all lists. "
        "Can filter by grocery list name, aisle, and purchased status.\n\n"
        "Each item shows its name, quantity, aisle, and item_id "
        "(needed for update_grocery and delete_grocery).\n\n"
        "Use without parameters to see what you need to buy."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "list": {
                "type": "string",
                "description": (
                    "Filter by grocery list name "
                    "(e.g., 'Costco', 'Whole Foods', 'My Grocery List'). "
                    "If not specified, shows items from all lists."
                ),
            },
            "aisle": {
                "type": "string",
                "description": (
                    "Filter by aisle name (e.g., 'Produce', 'Dairy'). "
                    "Partial match supported."
                ),
            },
            "show_purchased": {
                "type": "boolean",
                "description": (
                    "Include purchased (checked-off) items. "
                    "Default: false (only show items still to buy)."
                ),
                "default": False,
            },
        },
        "required": [],
    },
}

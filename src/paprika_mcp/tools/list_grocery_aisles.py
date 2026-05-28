"""List grocery aisles tool - retrieves all grocery aisles."""

from typing import Any

from mcp.types import TextContent

from ..utils import get_grocery_aisles, get_remote


async def list_grocery_aisles_tool(args: dict[str, Any]) -> list[TextContent]:
    """List all grocery aisles in Paprika."""
    remote = get_remote()
    aisles = get_grocery_aisles(remote.bearer_token)

    if not aisles:
        return [TextContent(type="text", text="No grocery aisles found.")]

    lines = [f"Found {len(aisles)} grocery aisles:\n"]
    for aisle in aisles:
        name = aisle.get("name", "Unnamed")
        lines.append(f"- {name}")

    return [TextContent(type="text", text="\n".join(lines))]


TOOL_DEFINITION = {
    "name": "list_grocery_aisles",
    "description": (
        "List all grocery aisles in Paprika. "
        "Shows aisle names in their configured order. "
        "Use this to find the correct aisle name for add_grocery or update_grocery."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

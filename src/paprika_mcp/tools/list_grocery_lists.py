"""List grocery lists tool - retrieves all grocery lists."""

from typing import Any

from mcp.types import TextContent

from ..utils import get_grocery_lists, get_remote


async def list_grocery_lists_tool(args: dict[str, Any]) -> list[TextContent]:
    """List all grocery lists in Paprika."""
    remote = get_remote()
    lists = get_grocery_lists(remote.bearer_token)

    if not lists:
        return [TextContent(type="text", text="No grocery lists found.")]

    lines = [f"Found {len(lists)} grocery lists:\n"]
    for gl in lists:
        name = gl.get("name", "Unnamed")
        default = " (default)" if gl.get("is_default") else ""
        lines.append(f"- **{name}**{default}")

    return [TextContent(type="text", text="\n".join(lines))]


TOOL_DEFINITION = {
    "name": "list_grocery_lists",
    "description": (
        "List all grocery lists in Paprika. "
        "Shows list names and which one is the default. "
        "Use this to find the correct list name for add_grocery or list_groceries."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

"""List meal types tool - retrieves all meal type definitions."""

from typing import Any

from mcp.types import TextContent

from ..utils import get_meal_types, get_remote


async def list_meal_types_tool(args: dict[str, Any]) -> list[TextContent]:
    """List all meal types in Paprika."""
    remote = get_remote()
    meal_types = get_meal_types(remote.bearer_token)

    if not meal_types:
        return [TextContent(type="text", text="No meal types found.")]

    lines = [f"Found {len(meal_types)} meal types:\n"]
    for mt in sorted(meal_types, key=lambda m: m.get("original_type", 0)):
        name = mt.get("name", "Unnamed")
        color = mt.get("color", "")
        export_time = mt.get("export_time", "")
        parts = [f"- **{name}**"]
        if export_time:
            parts.append(f"(export time: {export_time})")
        if color:
            parts.append(f"[color: {color}]")
        lines.append(" ".join(parts))

    return [TextContent(type="text", text="\n".join(lines))]


TOOL_DEFINITION = {
    "name": "list_meal_types",
    "description": (
        "List all meal types configured in Paprika (e.g., Breakfast, Lunch, Dinner). "
        "Shows type names, colors, and export times. "
        "Use this to find the correct meal type name for add_meal or update_meal."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

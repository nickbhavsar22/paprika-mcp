"""List meals tool - shows planned meals by date range."""

from datetime import date, timedelta
from typing import Any

from mcp.types import TextContent

from ..utils import (
    get_meals,
    get_remote,
    meal_type_int_to_name,
    resolve_date,
)


async def list_meals_tool(args: dict[str, Any]) -> list[TextContent]:
    """List planned meals, optionally filtered by date range and meal type."""
    date_single = args.get("date")
    date_from = args.get("date_from")
    date_to = args.get("date_to")
    meal_type_filter = args.get("meal_type")

    # Resolve dates
    try:
        if date_single:
            resolved = resolve_date(date_single)
            start_date = resolved
            end_date = resolved
        elif date_from or date_to:
            start_date = resolve_date(date_from) if date_from else None
            end_date = resolve_date(date_to) if date_to else None
        else:
            # Default: current week (today + 6 days)
            today = date.today()
            start_date = today.isoformat()
            end_date = (today + timedelta(days=6)).isoformat()
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    remote = get_remote()
    token = remote.bearer_token
    all_meals = get_meals(token)

    if not all_meals:
        return [TextContent(type="text", text="No meals found.")]

    # Filter by date range (compare first 10 chars: YYYY-MM-DD)
    filtered = all_meals
    if start_date:
        filtered = [m for m in filtered if m.get("date", "")[:10] >= start_date]
    if end_date:
        filtered = [m for m in filtered if m.get("date", "")[:10] <= end_date]

    # Filter by meal type
    if meal_type_filter:
        type_lower = meal_type_filter.lower()
        filtered = [
            m
            for m in filtered
            if meal_type_int_to_name(m.get("type", -1), token).lower() == type_lower
        ]

    if not filtered:
        range_desc = ""
        if date_single:
            range_desc = f" for {start_date}"
        elif start_date and end_date:
            range_desc = f" from {start_date} to {end_date}"
        elif start_date:
            range_desc = f" from {start_date} onward"
        elif end_date:
            range_desc = f" through {end_date}"
        type_desc = f" ({meal_type_filter})" if meal_type_filter else ""
        return [
            TextContent(
                type="text",
                text=f"No meals found{range_desc}{type_desc}.",
            )
        ]

    # Group by date
    by_date: dict[str, list[dict[str, Any]]] = {}
    for meal in filtered:
        meal_date = meal.get("date", "")[:10]
        by_date.setdefault(meal_date, []).append(meal)

    # Format output
    output_lines = [f"Found {len(filtered)} meals across {len(by_date)} days\n"]

    for meal_date in sorted(by_date.keys()):
        # Parse date for display
        try:
            d = date.fromisoformat(meal_date)
            display_date = d.strftime("%A, %B %d, %Y")
        except ValueError:
            display_date = meal_date

        output_lines.append(f"## {display_date}")

        # Group by meal type within this date
        by_type: dict[int, list[dict[str, Any]]] = {}
        for meal in by_date[meal_date]:
            t = meal.get("type", 0)
            by_type.setdefault(t, []).append(meal)

        for type_int in sorted(by_type.keys()):
            type_name = meal_type_int_to_name(type_int, token)
            output_lines.append(f"### {type_name}")
            for meal in by_type[type_int]:
                name = meal.get("name", "Unnamed")
                uid = meal.get("uid", "")
                recipe_uid = meal.get("recipe_uid")
                parts = [f"- {name}"]
                if recipe_uid:
                    parts.append(f"  (recipe: {recipe_uid})")
                parts.append(f"  [meal_id: {uid}]")
                output_lines.append("\n".join(parts))

        output_lines.append("")

    return [TextContent(type="text", text="\n".join(output_lines))]


TOOL_DEFINITION = {
    "name": "list_meals",
    "description": (
        "List planned meals, optionally filtered by date range and meal type. "
        "Shows the meal plan organized by date and meal type. "
        "Supports flexible date inputs: 'today', 'tomorrow', 'monday', "
        "'next friday', or 'YYYY-MM-DD'. "
        "If no dates are specified, shows the current week (today through 6 days out). "
        "Use 'date' for a single day, or 'date_from'/'date_to' for a range.\n\n"
        "Each meal entry shows its name, linked recipe UID (if any), and meal_id "
        "(needed for update_meal and delete_meal)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": (
                    "Show meals for a specific date. "
                    "Supports 'today', 'tomorrow', day names, or YYYY-MM-DD."
                ),
            },
            "date_from": {
                "type": "string",
                "description": (
                    "Start of date range (inclusive). "
                    "Supports 'today', 'tomorrow', day names, or YYYY-MM-DD."
                ),
            },
            "date_to": {
                "type": "string",
                "description": (
                    "End of date range (inclusive). "
                    "Supports 'today', 'tomorrow', day names, or YYYY-MM-DD."
                ),
            },
            "meal_type": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "snacks"],
                "description": "Filter to only this meal type.",
            },
        },
        "required": [],
    },
}

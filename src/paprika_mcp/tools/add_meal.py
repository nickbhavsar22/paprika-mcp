"""Add meal tool - creates a new meal in the meal plan."""

import uuid
from typing import Any

from mcp.types import TextContent

from ..utils import (
    get_remote,
    meal_type_name_to_int,
    meal_type_to_uid,
    resolve_date,
    save_meal,
)


async def add_meal_tool(args: dict[str, Any]) -> list[TextContent]:
    """Add a new meal to the meal plan."""
    name = args.get("name")
    date_str = args.get("date")
    meal_type_str = args.get("meal_type")
    recipe_id = args.get("recipe_id")
    order_flag = args.get("order_flag", 0)

    # Validate required fields
    if not name:
        return [TextContent(type="text", text="Error: 'name' is required.")]
    if not date_str:
        return [TextContent(type="text", text="Error: 'date' is required.")]
    if not meal_type_str:
        return [TextContent(type="text", text="Error: 'meal_type' is required.")]

    # Resolve date
    try:
        resolved_date = resolve_date(date_str)
    except ValueError as e:
        return [TextContent(type="text", text=f"Error: {e}")]

    # Resolve meal type
    remote = get_remote()
    token = remote.bearer_token
    type_int = meal_type_name_to_int(meal_type_str, token)
    if type_int is None:
        return [
            TextContent(
                type="text",
                text=f"Error: Unknown meal type '{meal_type_str}'. "
                "Use 'breakfast', 'lunch', 'dinner', or 'snacks'.",
            )
        ]

    type_uid = meal_type_to_uid(type_int, token)

    # Build meal data
    meal_uid = str(uuid.uuid4()).upper()
    meal_data: dict[str, Any] = {
        "uid": meal_uid,
        "name": name,
        "date": f"{resolved_date} 00:00:00",
        "type": type_int,
        "type_uid": type_uid,
        "recipe_uid": recipe_id,
        "order_flag": order_flag,
        "scale": None,
        "is_ingredient": False,
    }

    result = save_meal(token, meal_data)
    if not result["success"]:
        return [
            TextContent(
                type="text",
                text=f"Error creating meal: {result['error']}",
            )
        ]

    return [
        TextContent(
            type="text",
            text=(
                f"Meal created successfully.\n\n"
                f"**Name:** {name}\n"
                f"**Date:** {resolved_date}\n"
                f"**Type:** {meal_type_str}\n"
                f"**Meal ID:** {meal_uid}\n"
                + (f"**Linked Recipe:** {recipe_id}\n" if recipe_id else "")
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "add_meal",
    "description": (
        "Add a meal to the meal plan. Creates a new meal entry for a specific date "
        "and meal type. Can optionally link to an existing recipe by providing recipe_id. "
        "Supports flexible date inputs: 'today', 'tomorrow', 'monday', 'next friday', "
        "or 'YYYY-MM-DD'."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "Display name for the meal "
                    "(e.g., 'Chicken Parmesan', 'Leftover pasta')."
                ),
            },
            "date": {
                "type": "string",
                "description": (
                    "Date for the meal. Supports 'today', 'tomorrow', "
                    "day names, or YYYY-MM-DD."
                ),
            },
            "meal_type": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "snacks"],
                "description": "Type of meal.",
            },
            "recipe_id": {
                "type": "string",
                "description": (
                    "UID of an existing recipe to link to this meal. "
                    "Use search_recipes to find recipe IDs."
                ),
            },
            "order_flag": {
                "type": "integer",
                "description": (
                    "Order within the same date and meal type (default: 0). "
                    "Higher values appear later."
                ),
                "default": 0,
            },
        },
        "required": ["name", "date", "meal_type"],
    },
}

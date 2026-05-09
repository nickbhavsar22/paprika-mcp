"""Delete meal tool - removes a meal from the meal plan."""

from typing import Any

from mcp.types import TextContent

from ..utils import get_meals, get_remote, meal_type_int_to_name, save_meal


async def delete_meal_tool(args: dict[str, Any]) -> list[TextContent]:
    """Delete a meal from the meal plan (soft delete)."""
    meal_id = args.get("meal_id")

    if not meal_id:
        return [TextContent(type="text", text="Error: 'meal_id' is required.")]

    remote = get_remote()
    token = remote.bearer_token
    all_meals = get_meals(token)

    # Find the meal
    meal = None
    for m in all_meals:
        if m.get("uid") == meal_id:
            meal = m
            break

    if not meal:
        return [
            TextContent(
                type="text",
                text=f"Error: No meal found with ID '{meal_id}'.",
            )
        ]

    # Capture info for confirmation before deleting
    name = meal.get("name", "Unnamed")
    meal_date = meal.get("date", "")[:10]
    type_name = meal_type_int_to_name(meal.get("type", -1), token)

    # Soft delete
    meal["deleted"] = True
    result = save_meal(token, meal)
    if not result["success"]:
        return [
            TextContent(
                type="text",
                text=f"Error deleting meal: {result['error']}",
            )
        ]

    return [
        TextContent(
            type="text",
            text=(
                f"Meal deleted successfully.\n\n"
                f"**Name:** {name}\n"
                f"**Date:** {meal_date}\n"
                f"**Type:** {type_name}"
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "delete_meal",
    "description": (
        "Remove a meal from the meal plan. "
        "This is a DANGEROUS operation that requires user confirmation. "
        "Use list_meals to find meal IDs before deleting."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "meal_id": {
                "type": "string",
                "description": (
                    "UID of the meal to delete. "
                    "Use list_meals to find meal IDs."
                ),
            },
        },
        "required": ["meal_id"],
    },
}

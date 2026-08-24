"""Update meal tool - modifies an existing meal's properties."""

from typing import Any

from mcp.types import TextContent

from ..utils import (
    get_meals,
    get_remote,
    meal_type_int_to_name,
    meal_type_name_to_int,
    meal_type_to_uid,
    resolve_date,
    save_meal,
)


async def update_meal_tool(args: dict[str, Any]) -> list[TextContent]:
    """Update an existing meal's properties."""
    meal_id = args.get("meal_id")
    new_name = args.get("name")
    new_date = args.get("date")
    new_type = args.get("meal_type")
    new_recipe_id = args.get("recipe_id")
    new_order = args.get("order_flag")

    if not meal_id:
        return [TextContent(type="text", text="Error: 'meal_id' is required.")]

    # Check that at least one field is being updated
    if all(v is None for v in [new_name, new_date, new_type, new_recipe_id, new_order]):
        return [
            TextContent(
                type="text",
                text="Error: Provide at least one field to update "
                "(name, date, meal_type, recipe_id, or order_flag).",
            )
        ]

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

    # Track changes for the confirmation message
    changes = []

    # Apply updates
    if new_name is not None:
        changes.append(f"Name: '{meal.get('name')}' -> '{new_name}'")
        meal["name"] = new_name

    if new_date is not None:
        try:
            resolved = resolve_date(new_date)
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]
        old_date = meal.get("date", "")[:10]
        changes.append(f"Date: {old_date} -> {resolved}")
        meal["date"] = f"{resolved} 00:00:00"

    if new_type is not None:
        type_int = meal_type_name_to_int(new_type, token)
        if type_int is None:
            return [
                TextContent(
                    type="text",
                    text=f"Error: Unknown meal type '{new_type}'. "
                    "Use 'breakfast', 'lunch', 'dinner', or 'snacks'.",
                )
            ]
        old_type = meal_type_int_to_name(meal.get("type", -1), token)
        changes.append(f"Type: {old_type} -> {new_type}")
        meal["type"] = type_int
        meal["type_uid"] = meal_type_to_uid(type_int, token)

    if new_recipe_id is not None:
        old_recipe = meal.get("recipe_uid") or "(none)"
        new_display = new_recipe_id if new_recipe_id else "(unlinked)"
        changes.append(f"Recipe: {old_recipe} -> {new_display}")
        meal["recipe_uid"] = new_recipe_id if new_recipe_id else None

    if new_order is not None:
        changes.append(f"Order: {meal.get('order_flag')} -> {new_order}")
        meal["order_flag"] = new_order

    result = save_meal(token, meal)
    if not result["success"]:
        return [
            TextContent(
                type="text",
                text=f"Error updating meal: {result['error']}",
            )
        ]

    changes_text = "\n".join(f"- {c}" for c in changes)
    return [
        TextContent(
            type="text",
            text=(
                f"Meal '{meal.get('name')}' updated successfully.\n\n"
                f"Changes:\n{changes_text}"
            ),
        )
    ]


TOOL_DEFINITION = {
    "name": "update_meal",
    "description": (
        "Update an existing meal's properties. Can change name, date, meal type, "
        "linked recipe, or order. Moving a meal to a different date is done by "
        "updating the 'date' field. Only provided fields are changed; omitted fields "
        "keep their current values.\n\n"
        "Use list_meals to find meal IDs. "
        "To unlink a recipe from a meal, set recipe_id to an empty string ''."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "meal_id": {
                "type": "string",
                "description": (
                    "UID of the meal to update. Use list_meals to find meal IDs."
                ),
            },
            "name": {
                "type": "string",
                "description": "New display name for the meal.",
            },
            "date": {
                "type": "string",
                "description": (
                    "New date for the meal (moves it). Supports 'today', "
                    "'tomorrow', day names, or YYYY-MM-DD."
                ),
            },
            "meal_type": {
                "type": "string",
                "enum": ["breakfast", "lunch", "dinner", "snacks"],
                "description": "New meal type.",
            },
            "recipe_id": {
                "type": "string",
                "description": (
                    "New recipe UID to link. " "Use empty string '' to unlink a recipe."
                ),
            },
            "order_flag": {
                "type": "integer",
                "description": "New order within the same date and meal type.",
            },
        },
        "required": ["meal_id"],
    },
}

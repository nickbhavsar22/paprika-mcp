"""Update recipe tool - modifies recipe fields using find/replace."""

import re
from typing import Any

from mcp.types import TextContent

from ..utils import find_recipe_by_id, get_remote

ALLOWED_TEXT_FIELDS = {
    "name",
    "ingredients",
    "directions",
    "notes",
    "description",
    "source",
    "source_url",
    "prep_time",
    "cook_time",
    "total_time",
    "servings",
    "difficulty",
    "nutritional_info",
}


def is_updateable_text_field(field: str) -> bool:
    """Return True when a field supports string replacement."""
    return field in ALLOWED_TEXT_FIELDS


async def update_recipe_tool(args: dict[str, Any]) -> list[TextContent]:
    """Update recipe fields using find/replace - DANGEROUS operation."""
    recipe_id = args.get("id")
    field = args.get("field")
    find = args.get("find")
    replace = args.get("replace")
    use_regex = bool(args.get("regex", False))

    missing = [
        key
        for key, val in (
            ("id", recipe_id),
            ("field", field),
            ("find", find),
            ("replace", replace),
        )
        if val is None
    ]
    if missing:
        return [
            TextContent(
                type="text",
                text=f"Error: missing required argument(s): {', '.join(missing)}.",
            )
        ]

    field = str(field)
    find = str(find)
    replace = str(replace)

    # Get the remote
    remote = get_remote()

    # Fetch the recipe
    recipe = find_recipe_by_id(remote, str(recipe_id))

    if not recipe:
        return [
            TextContent(
                type="text",
                text=f"Error: No recipe found with ID '{recipe_id}'",
            )
        ]

    if not is_updateable_text_field(field):
        return [
            TextContent(
                type="text",
                text=(
                    f"Error: Field '{field}' cannot be updated with find/replace. "
                    "Only text fields are supported."
                ),
            )
        ]

    # Get the current field value
    field_value = getattr(recipe, field, None)

    if field_value is None:
        return [
            TextContent(
                type="text",
                text=f"Error: Recipe '{recipe.name}' does not have field '{field}'",
            )
        ]

    # Perform the find/replace
    if not isinstance(field_value, str):
        return [
            TextContent(
                type="text",
                text=(
                    f"Error: Field '{field}' on recipe '{recipe.name}' is not text "
                    "and cannot be updated with find/replace."
                ),
            )
        ]

    if use_regex:
        try:
            new_value = re.sub(find, replace, field_value)
        except re.error as e:
            return [
                TextContent(
                    type="text", text=f"Error: Invalid regex pattern '{find}': {str(e)}"
                )
            ]
    else:
        new_value = field_value.replace(find, replace)

    # Check if anything changed
    if new_value == field_value:
        return [
            TextContent(
                type="text",
                text=f"No changes made - pattern '{find}' not found in field '{field}' of recipe '{recipe.name}'",
            )
        ]

    # Update the field
    setattr(recipe, field, new_value)

    # Save the recipe
    try:
        remote.upload_recipe(recipe)
        return [
            TextContent(
                type="text",
                text=f"Successfully updated field '{field}' in recipe '{recipe.name}' (ID: {recipe_id})\n\nOld value:\n{field_value}\n\nNew value:\n{new_value}",
            )
        ]
    except Exception as e:
        return [
            TextContent(
                type="text", text=f"Error updating recipe '{recipe.name}': {str(e)}"
            )
        ]


# Tool definition
TOOL_DEFINITION = {
    "name": "update_recipe",
    "description": (
        "Update recipe fields using find/replace. "
        "This is a DANGEROUS operation that requires user confirmation. "
        "Can update any text field in a recipe."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Recipe UID to update"},
            "field": {
                "type": "string",
                "enum": [
                    "name",
                    "ingredients",
                    "directions",
                    "notes",
                    "description",
                    "source",
                    "source_url",
                    "prep_time",
                    "cook_time",
                    "total_time",
                    "servings",
                    "difficulty",
                    "nutritional_info",
                ],
                "description": "Field to update",
            },
            "find": {"type": "string", "description": "Text to find in the field"},
            "replace": {"type": "string", "description": "Text to replace it with"},
            "regex": {
                "type": "boolean",
                "description": "Whether to treat 'find' as a regex pattern (default: false)",
                "default": False,
            },
        },
        "required": ["id", "field", "find", "replace"],
    },
}

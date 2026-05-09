"""Tools module - exports all MCP tool implementations."""

from .add_meal import TOOL_DEFINITION as ADD_MEAL_DEF
from .add_meal import add_meal_tool
from .delete_meal import TOOL_DEFINITION as DELETE_MEAL_DEF
from .delete_meal import delete_meal_tool
from .format_fraction import TOOL_DEFINITION as FORMAT_FRACTION_DEF
from .format_fraction import format_fraction_tool
from .list_categories import TOOL_DEFINITION as LIST_CATEGORIES_DEF
from .list_categories import list_categories_tool
from .list_meals import TOOL_DEFINITION as LIST_MEALS_DEF
from .list_meals import list_meals_tool
from .read_recipe import TOOL_DEFINITION as READ_RECIPE_DEF
from .read_recipe import read_recipe_tool
from .search_recipes import TOOL_DEFINITION as SEARCH_RECIPES_DEF
from .search_recipes import search_recipes_tool
from .update_meal import TOOL_DEFINITION as UPDATE_MEAL_DEF
from .update_meal import update_meal_tool
from .update_recipe import TOOL_DEFINITION as UPDATE_RECIPE_DEF
from .update_recipe import update_recipe_tool

# Export all tools and their definitions
TOOLS = {
    "search_recipes": {
        "definition": SEARCH_RECIPES_DEF,
        "handler": search_recipes_tool,
    },
    "read_recipe": {
        "definition": READ_RECIPE_DEF,
        "handler": read_recipe_tool,
    },
    "update_recipe": {
        "definition": UPDATE_RECIPE_DEF,
        "handler": update_recipe_tool,
    },
    "list_categories": {
        "definition": LIST_CATEGORIES_DEF,
        "handler": list_categories_tool,
    },
    "format_fraction": {
        "definition": FORMAT_FRACTION_DEF,
        "handler": format_fraction_tool,
    },
    "list_meals": {
        "definition": LIST_MEALS_DEF,
        "handler": list_meals_tool,
    },
    "add_meal": {
        "definition": ADD_MEAL_DEF,
        "handler": add_meal_tool,
    },
    "update_meal": {
        "definition": UPDATE_MEAL_DEF,
        "handler": update_meal_tool,
    },
    "delete_meal": {
        "definition": DELETE_MEAL_DEF,
        "handler": delete_meal_tool,
    },
}

__all__ = [
    "TOOLS",
    "search_recipes_tool",
    "read_recipe_tool",
    "update_recipe_tool",
    "list_categories_tool",
    "format_fraction_tool",
    "list_meals_tool",
    "add_meal_tool",
    "update_meal_tool",
    "delete_meal_tool",
]

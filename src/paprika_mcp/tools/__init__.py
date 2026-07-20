"""Tools module - exports all MCP tool implementations."""

from .add_grocery import TOOL_DEFINITION as ADD_GROCERY_DEF
from .add_grocery import add_grocery_tool
from .add_meal import TOOL_DEFINITION as ADD_MEAL_DEF
from .add_meal import add_meal_tool
from .create_category import TOOL_DEFINITION as CREATE_CATEGORY_DEF
from .create_category import create_category_tool
from .create_recipe import TOOL_DEFINITION as CREATE_RECIPE_DEF
from .create_recipe import create_recipe_tool
from .delete_category import TOOL_DEFINITION as DELETE_CATEGORY_DEF
from .delete_category import delete_category_tool
from .delete_grocery import TOOL_DEFINITION as DELETE_GROCERY_DEF
from .delete_grocery import delete_grocery_tool
from .delete_meal import TOOL_DEFINITION as DELETE_MEAL_DEF
from .delete_meal import delete_meal_tool
from .delete_recipe import TOOL_DEFINITION as DELETE_RECIPE_DEF
from .delete_recipe import delete_recipe_tool
from .format_fraction import TOOL_DEFINITION as FORMAT_FRACTION_DEF
from .format_fraction import format_fraction_tool
from .get_photo_upload_link import TOOL_DEFINITION as GET_PHOTO_UPLOAD_LINK_DEF
from .get_photo_upload_link import get_photo_upload_link_tool
from .list_categories import TOOL_DEFINITION as LIST_CATEGORIES_DEF
from .list_categories import list_categories_tool
from .list_groceries import TOOL_DEFINITION as LIST_GROCERIES_DEF
from .list_groceries import list_groceries_tool
from .list_grocery_aisles import TOOL_DEFINITION as LIST_GROCERY_AISLES_DEF
from .list_grocery_aisles import list_grocery_aisles_tool
from .list_grocery_lists import TOOL_DEFINITION as LIST_GROCERY_LISTS_DEF
from .list_grocery_lists import list_grocery_lists_tool
from .list_meal_types import TOOL_DEFINITION as LIST_MEAL_TYPES_DEF
from .list_meal_types import list_meal_types_tool
from .list_meals import TOOL_DEFINITION as LIST_MEALS_DEF
from .list_meals import list_meals_tool
from .read_recipe import TOOL_DEFINITION as READ_RECIPE_DEF
from .read_recipe import read_recipe_tool
from .search_recipes import TOOL_DEFINITION as SEARCH_RECIPES_DEF
from .search_recipes import search_recipes_tool
from .set_recipe_photo import TOOL_DEFINITION as SET_RECIPE_PHOTO_DEF
from .set_recipe_photo import set_recipe_photo_tool
from .update_grocery import TOOL_DEFINITION as UPDATE_GROCERY_DEF
from .update_grocery import update_grocery_tool
from .update_meal import TOOL_DEFINITION as UPDATE_MEAL_DEF
from .update_meal import update_meal_tool
from .update_recipe import TOOL_DEFINITION as UPDATE_RECIPE_DEF
from .update_recipe import update_recipe_tool
from .update_recipe_categories import TOOL_DEFINITION as UPDATE_RECIPE_CATEGORIES_DEF
from .update_recipe_categories import update_recipe_categories_tool

# Export all tools and their definitions
TOOLS = {
    "create_recipe": {
        "definition": CREATE_RECIPE_DEF,
        "handler": create_recipe_tool,
    },
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
    "update_recipe_categories": {
        "definition": UPDATE_RECIPE_CATEGORIES_DEF,
        "handler": update_recipe_categories_tool,
    },
    "delete_recipe": {
        "definition": DELETE_RECIPE_DEF,
        "handler": delete_recipe_tool,
    },
    "set_recipe_photo": {
        "definition": SET_RECIPE_PHOTO_DEF,
        "handler": set_recipe_photo_tool,
    },
    "get_photo_upload_link": {
        "definition": GET_PHOTO_UPLOAD_LINK_DEF,
        "handler": get_photo_upload_link_tool,
    },
    "list_categories": {
        "definition": LIST_CATEGORIES_DEF,
        "handler": list_categories_tool,
    },
    "create_category": {
        "definition": CREATE_CATEGORY_DEF,
        "handler": create_category_tool,
    },
    "delete_category": {
        "definition": DELETE_CATEGORY_DEF,
        "handler": delete_category_tool,
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
    "list_groceries": {
        "definition": LIST_GROCERIES_DEF,
        "handler": list_groceries_tool,
    },
    "list_grocery_lists": {
        "definition": LIST_GROCERY_LISTS_DEF,
        "handler": list_grocery_lists_tool,
    },
    "list_grocery_aisles": {
        "definition": LIST_GROCERY_AISLES_DEF,
        "handler": list_grocery_aisles_tool,
    },
    "list_meal_types": {
        "definition": LIST_MEAL_TYPES_DEF,
        "handler": list_meal_types_tool,
    },
    "add_grocery": {
        "definition": ADD_GROCERY_DEF,
        "handler": add_grocery_tool,
    },
    "update_grocery": {
        "definition": UPDATE_GROCERY_DEF,
        "handler": update_grocery_tool,
    },
    "delete_grocery": {
        "definition": DELETE_GROCERY_DEF,
        "handler": delete_grocery_tool,
    },
}

__all__ = [
    "TOOLS",
    "add_grocery_tool",
    "add_meal_tool",
    "create_category_tool",
    "create_recipe_tool",
    "delete_category_tool",
    "delete_grocery_tool",
    "delete_meal_tool",
    "delete_recipe_tool",
    "format_fraction_tool",
    "get_photo_upload_link_tool",
    "list_categories_tool",
    "list_groceries_tool",
    "list_grocery_aisles_tool",
    "list_grocery_lists_tool",
    "list_meal_types_tool",
    "list_meals_tool",
    "read_recipe_tool",
    "search_recipes_tool",
    "set_recipe_photo_tool",
    "update_grocery_tool",
    "update_meal_tool",
    "update_recipe_categories_tool",
    "update_recipe_tool",
]

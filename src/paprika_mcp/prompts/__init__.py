"""Prompts module - exports all MCP prompt implementations."""

from .set_recipe_thumbnail import PROMPT_DEFINITION as SET_RECIPE_THUMBNAIL_DEF
from .set_recipe_thumbnail import set_recipe_thumbnail_prompt
from .user_preferences import PROMPT_DEFINITION as USER_PREFS_DEF
from .user_preferences import user_preferences_prompt

# Export all prompts and their definitions
PROMPTS = {
    "user_preferences": {
        "definition": USER_PREFS_DEF,
        "handler": user_preferences_prompt,
    },
    "set_recipe_thumbnail": {
        "definition": SET_RECIPE_THUMBNAIL_DEF,
        "handler": set_recipe_thumbnail_prompt,
    },
}

__all__ = [
    "PROMPTS",
    "set_recipe_thumbnail_prompt",
    "user_preferences_prompt",
]

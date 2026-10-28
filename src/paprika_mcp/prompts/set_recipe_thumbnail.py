"""Thumbnail sourcing prompt - free image first, generation only as a fallback.

Tiers 1 and 2 are tools on this server (`find_free_thumbnail`, then
`generate_thumbnail`, which calls OpenAI's image model itself). Tier 3 runs on
the Higgsfield MCP that the client may have connected; this server can't call
it, so that step is expressed as instructions for the assistant.
"""

from typing import Any

from mcp.types import GetPromptResult, PromptMessage, TextContent

INSTRUCTIONS = """\
# Setting a recipe thumbnail

Work through these tiers **in order** and stop at the first one that produces a
good image. Cost rises at every step, so never skip ahead.

## 0. Check whether one is even needed
Call `read_recipe` with `fields=["photo"]`. If it reports **Has thumbnail: yes**,
stop and say so — only continue if the user explicitly asked to replace it.

## 1. Free — find a real photo (always try this first)
Call `find_free_thumbnail` with the recipe's `id`.

- It searches the recipe's own source page, any linked YouTube video, a web
  image search, and Wikimedia Commons.
- If it returns a candidate marked as a good candidate, attach it:
  `set_recipe_photo(id=<recipe id>, image_url=<candidate url>)`. **Done.**
- If the candidate is weak, show the user the URL and ask whether to use it
  before spending money on generation.
- If nothing is found, go to tier 2.

## 2. Generate with ChatGPT Images (OpenAI) — `generate_thumbnail`
Only if tier 1 found nothing usable.

Call `generate_thumbnail(id=<recipe id>)`. It builds the food-photo prompt from
the recipe, generates the image with OpenAI's gpt-image-2, and attaches it in
one step (about $0.06 at the default medium quality). Pass `dish_description` if
the recipe's own description is missing or unhelpful. **Done.**

If it reports it isn't configured, or that generation failed, go to tier 3.

## 3. Generate with the Higgsfield MCP
Only if tiers 1 and 2 both failed. Use the Higgsfield image generation tool with
the prompt template below (`generate_thumbnail`'s failure message includes the
filled-in prompt), then attach the returned URL with `set_recipe_photo`.

If Higgsfield isn't connected either, tell the user no thumbnail could be
sourced and what they can do (give you an image URL, or upload a photo — call
`get_photo_upload_link` for that).

## Image generation prompt template

    Professional food photography of {recipe name}.
    {one-line description of the finished dish, from the recipe}
    Overhead three-quarter angle, natural window light, shallow depth of field,
    served on a simple ceramic dish, or in fitting glassware for a drink,
    against a clean neutral background.
    Appetizing, realistic, high detail. No text, no logos, no hands, no utensils
    in frame.

Fill `{recipe name}` and the description from the recipe itself (read it first if
you haven't). Keep it photorealistic — Paprika thumbnails should look like food
photos, not illustrations.

## Rules
- Generation costs money. Confirm with the user before tier 2 or 3 unless they've
  already said to go ahead.
- `set_recipe_photo` modifies real recipe data — confirm before attaching.
- Never invent an image URL. Only attach URLs that a tool actually returned.
"""


async def set_recipe_thumbnail_prompt(args: dict[str, Any]) -> GetPromptResult:
    """Return the tiered thumbnail-sourcing workflow."""
    recipe = args.get("recipe")
    text = INSTRUCTIONS
    if recipe:
        text = f"{INSTRUCTIONS}\n---\n\nApply this to the recipe: **{recipe}**\n"

    return GetPromptResult(
        description="Source a recipe thumbnail: free image first, generate only if needed",
        messages=[
            PromptMessage(role="user", content=TextContent(type="text", text=text))
        ],
    )


PROMPT_DEFINITION = {
    "name": "set_recipe_thumbnail",
    "description": (
        "Workflow for giving a recipe a thumbnail: try to find a free real photo "
        "first, then generate one with ChatGPT Images (`generate_thumbnail`), and "
        "only fall back to Higgsfield if that's unavailable."
    ),
    "arguments": [
        {
            "name": "recipe",
            "description": "Recipe name or UID to set a thumbnail for (optional).",
            "required": False,
        }
    ],
}

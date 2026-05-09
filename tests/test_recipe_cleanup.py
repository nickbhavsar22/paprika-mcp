import unittest

from paprika_recipes.remote import RemoteRecipe

from paprika_mcp.recipe_maintenance import (
    build_description_with_links,
    build_recipe_plan,
    clean_ingredients,
    clean_instructions,
    extract_youtube_id,
    youtube_thumbnail,
)


class RecipeCleanupTests(unittest.TestCase):
    def test_clean_ingredients_normalizes_bullets_and_strips_timestamps(self):
        text = "00:15 - 1 cup flour\n* 2 eggs\nIngredients:"

        cleaned = clean_ingredients(text)

        self.assertEqual(cleaned, "- 1 cup flour\n- 2 eggs")

    def test_clean_instructions_numbers_steps(self):
        text = "00:10 - Mix the batter.\n\n2) Bake for 20 minutes."

        cleaned = clean_instructions(text)

        self.assertEqual(cleaned, "1. Mix the batter.\n2. Bake for 20 minutes.")

    def test_build_description_with_links_adds_missing_links_once(self):
        description, additions = build_description_with_links(
            "Tasty soup",
            "https://example.com/recipe",
            "https://youtube.com/watch?v=abc123",
        )

        self.assertIn("Source: https://example.com/recipe", description)
        self.assertIn("Video: https://youtube.com/watch?v=abc123", description)
        self.assertEqual(len(additions), 2)

        description_again, additions_again = build_description_with_links(
            description,
            "https://example.com/recipe",
            "https://youtube.com/watch?v=abc123",
        )

        self.assertEqual(description, description_again)
        self.assertEqual(additions_again, [])

    def test_youtube_thumbnail(self):
        self.assertEqual(
            extract_youtube_id("https://www.youtube.com/watch?v=abc123XYZ"),
            "abc123XYZ",
        )
        self.assertEqual(
            youtube_thumbnail("https://youtu.be/abc123XYZ"),
            "https://img.youtube.com/vi/abc123XYZ/hqdefault.jpg",
        )

    def test_build_recipe_plan_flags_serving_hint(self):
        recipe = RemoteRecipe(
            uid="ABC",
            name="Test Soup",
            ingredients="1 cup water",
            directions="Mix well.",
            notes="Serves 4",
            servings="2",
        )

        plan = build_recipe_plan(recipe, include_thumbnail=False)

        self.assertEqual(plan.updates["servings"], "4")
        self.assertEqual(plan.audit.status, "needs_review")


if __name__ == "__main__":
    unittest.main()

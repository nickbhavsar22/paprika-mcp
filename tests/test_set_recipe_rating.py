"""Tests for set_recipe_rating. The Paprika API is mocked throughout."""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from paprika_recipes.remote import RemoteRecipe

from paprika_mcp.tools import TOOLS
from paprika_mcp.tools.set_recipe_rating import parse_rating, set_recipe_rating_tool

MODULE = "paprika_mcp.tools.set_recipe_rating"


def run(args):
    return asyncio.run(set_recipe_rating_tool(args))[0].text


class ParseRatingTests(unittest.TestCase):
    def test_accepts_whole_numbers_zero_to_five(self):
        for value, expected in [(0, 0), (5, 5), (4.0, 4), ("3", 3), (" 2 ", 2)]:
            self.assertEqual(parse_rating(value), expected, value)

    def test_rejects_everything_else(self):
        for value in [6, -1, 3.5, "4.5", "five", "", None, True, False, [4]]:
            self.assertIsNone(parse_rating(value), value)


class SetRecipeRatingTests(unittest.TestCase):
    def setUp(self):
        self.recipe = RemoteRecipe(uid="U1", name="Lasagna", rating=2)
        self.remote = MagicMock()
        patcher_remote = patch(f"{MODULE}.get_remote", return_value=self.remote)
        patcher_find = patch(f"{MODULE}.find_recipe_by_id", return_value=self.recipe)
        self.find = patcher_find.start()
        patcher_remote.start()
        self.addCleanup(patch.stopall)

    def test_sets_rating_and_uploads(self):
        text = run({"id": "U1", "rating": 5})
        self.assertEqual(self.recipe.rating, 5)
        self.remote.upload_recipe.assert_called_once_with(self.recipe)
        self.assertIn("2/5", text)
        self.assertIn("5/5", text)

    def test_zero_clears_the_rating(self):
        text = run({"id": "U1", "rating": 0})
        self.assertEqual(self.recipe.rating, 0)
        self.assertIn("unrated", text)

    def test_unchanged_rating_skips_the_upload(self):
        text = run({"id": "U1", "rating": 2})
        self.remote.upload_recipe.assert_not_called()
        self.assertIn("No change", text)

    def test_invalid_rating_never_touches_the_api(self):
        text = run({"id": "U1", "rating": 7})
        self.assertIn("whole number from 0 to 5", text)
        self.find.assert_not_called()
        self.remote.upload_recipe.assert_not_called()

    def test_missing_id_is_rejected(self):
        self.assertIn("'id' is required", run({"rating": 4}))

    def test_unknown_recipe_is_reported(self):
        self.find.return_value = None
        self.assertIn("No recipe found", run({"id": "NOPE", "rating": 4}))
        self.remote.upload_recipe.assert_not_called()

    def test_upload_failure_is_reported(self):
        self.remote.upload_recipe.side_effect = RuntimeError("boom")
        self.assertIn("Error updating rating", run({"id": "U1", "rating": 4}))

    def test_tool_is_registered(self):
        self.assertIs(TOOLS["set_recipe_rating"]["handler"], set_recipe_rating_tool)


if __name__ == "__main__":
    unittest.main()

import unittest

from paprika_mcp.tools.search_recipes import validate_pagination
from paprika_mcp.tools.update_recipe import is_updateable_text_field


class ToolValidationTests(unittest.TestCase):
    def test_validate_pagination(self):
        self.assertIsNone(validate_pagination(1, 20))
        self.assertEqual(
            validate_pagination(0, 20), "Error: 'page' must be an integer >= 1"
        )
        self.assertEqual(
            validate_pagination(1, 0),
            "Error: 'page_size' must be an integer >= 1",
        )

    def test_updateable_text_fields(self):
        self.assertTrue(is_updateable_text_field("ingredients"))
        self.assertTrue(is_updateable_text_field("servings"))
        self.assertFalse(is_updateable_text_field("rating"))
        self.assertFalse(is_updateable_text_field("categories"))


if __name__ == "__main__":
    unittest.main()

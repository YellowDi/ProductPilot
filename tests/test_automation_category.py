from __future__ import annotations

import unittest

from product_pilot.automation.category import format_category_path, parse_category_path


class CategoryTests(unittest.TestCase):
    def test_parses_category_path(self) -> None:
        self.assertEqual(
            parse_category_path("流行男鞋 > 低帮鞋 > 板鞋"),
            ("流行男鞋", "低帮鞋", "板鞋"),
        )

    def test_parses_slash_separator(self) -> None:
        self.assertEqual(
            parse_category_path("流行男鞋/低帮鞋/板鞋"),
            ("流行男鞋", "低帮鞋", "板鞋"),
        )

    def test_formats_category_path(self) -> None:
        self.assertEqual(
            format_category_path(("流行男鞋", "低帮鞋", "板鞋")),
            "流行男鞋 > 低帮鞋 > 板鞋",
        )


if __name__ == "__main__":
    unittest.main()


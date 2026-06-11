from __future__ import annotations

import unittest

from product_pilot.automation.category import (
    dismiss_recommended_category_modals,
    format_category_path,
    parse_category_path,
    select_category,
)


class FakeCategoryPage:
    def __init__(self, recommended_modal_count: int = 1, delayed_empty_checks: int = 0) -> None:
        self.evaluate_calls: list[str] = []
        self.delayed_empty_checks = delayed_empty_checks
        self.recommended_modal_count = recommended_modal_count
        self.waits: list[int] = []

    def evaluate(self, script: str, arg: object | None = None) -> bool | str:
        self.evaluate_calls.append(script)
        if "建议商品分类" in script:
            if self.delayed_empty_checks > 0:
                self.delayed_empty_checks -= 1
                return ""
            if self.recommended_modal_count > 0:
                self.recommended_modal_count -= 1
                return "关闭"
        if "targetText = normalize(target)" in script:
            return True
        return False

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


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

    def test_dismisses_recommended_modal_before_configured_category(self) -> None:
        page = FakeCategoryPage()

        result = select_category(page, ("流行男鞋", "低帮鞋", "板鞋"))

        self.assertFalse(result.selected_from_recommendation)
        self.assertIn("dismissed recommended category modal: 关闭", result.notes)
        self.assertIn(
            "selected recent category: 流行男鞋 > 低帮鞋 > 板鞋",
            result.notes,
        )
        self.assertEqual(page.waits, [500, 1_000])

    def test_dismisses_multiple_recommended_modals(self) -> None:
        page = FakeCategoryPage(recommended_modal_count=3)
        notes: list[str] = []

        dismissed = dismiss_recommended_category_modals(page, notes)

        self.assertEqual(dismissed, 3)
        self.assertEqual(notes, ["dismissed recommended category modal: 关闭"] * 3)
        self.assertEqual(page.waits, [500, 500, 500])

    def test_waits_for_delayed_recommended_modal(self) -> None:
        page = FakeCategoryPage(recommended_modal_count=1, delayed_empty_checks=1)
        notes: list[str] = []

        dismissed = dismiss_recommended_category_modals(page, notes)

        self.assertEqual(dismissed, 1)
        self.assertEqual(notes, ["dismissed recommended category modal: 关闭"])
        self.assertEqual(page.waits, [250, 500])


if __name__ == "__main__":
    unittest.main()

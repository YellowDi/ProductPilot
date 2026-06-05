from __future__ import annotations

import unittest

from product_pilot.automation.field_scan import extract_required_labels


class FieldScanTests(unittest.TestCase):
    def test_extracts_required_labels(self) -> None:
        labels = extract_required_labels(
            [
                "*商品标题",
                "*商品轮播图 图片要求",
                "第2步 *选择商品分类",
            ]
        )

        self.assertIn("商品标题", labels)
        self.assertIn("商品轮播图 图片要求", labels)
        self.assertIn("选择商品分类", labels)

    def test_deduplicates_required_labels(self) -> None:
        labels = extract_required_labels(["*商品标题", "*商品标题"])

        self.assertEqual(labels, ["商品标题"])


if __name__ == "__main__":
    unittest.main()


from __future__ import annotations

import unittest

from product_pilot.domain.product import ProductDraft


class ProductDraftTests(unittest.TestCase):
    def test_valid_product_draft(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Test Product",
                "category": "default-category",
                "images": [{"path": "images/main.jpg", "role": "main"}],
                "skus": [{"name": "default", "price": "19.90", "stock": 10}],
            }
        )

        self.assertEqual(product.validate(), [])

    def test_requires_main_image(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Test Product",
                "category": "default-category",
                "images": [{"path": "images/detail.jpg", "role": "detail"}],
                "skus": [{"name": "default", "price": "19.90", "stock": 10}],
            }
        )

        self.assertIn("at least one main image is required", product.validate())

    def test_rejects_invalid_sku_values(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Test Product",
                "category": "default-category",
                "images": [{"path": "images/main.jpg", "role": "main"}],
                "skus": [{"name": "", "price": "0", "stock": -1}],
            }
        )

        errors = product.validate()
        self.assertIn("skus[1].sku.name is required", errors)
        self.assertIn("skus[1].sku.price must be greater than 0: <empty>", errors)
        self.assertIn("skus[1].sku.stock must be greater than or equal to 0: <empty>", errors)


if __name__ == "__main__":
    unittest.main()


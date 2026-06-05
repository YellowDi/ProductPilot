from __future__ import annotations

import unittest

from product_pilot.domain.product import ProductDraft


class ProductDraftTests(unittest.TestCase):
    def test_valid_product_draft(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Test Product",
                "category": "default-category",
                "images": [
                    {"path": "images/main.jpg", "role": "main"},
                    {"path": "images/detail.jpg", "role": "detail"},
                    {"path": "images/sku.jpg", "role": "sku"},
                ],
                "skus": [{"name": "default", "price": "19.90", "stock": 10}],
            }
        )

        self.assertEqual(product.validate(), [])

    def test_parses_optional_sku_prices(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Test Product",
                "category": "default-category",
                "images": [{"path": "images/main.jpg", "role": "main"}],
                "skus": [
                    {
                        "name": "42",
                        "price": "29.90",
                        "single_price": "39.90",
                        "reference_price": "99.00",
                        "stock": 10,
                    }
                ],
            }
        )

        self.assertEqual(product.validate(), [])
        self.assertEqual(str(product.skus[0].single_price), "39.90")
        self.assertEqual(str(product.skus[0].reference_price), "99.00")

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

    def test_requires_image_path(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Test Product",
                "category": "default-category",
                "images": [{"path": "", "role": "main"}],
                "skus": [{"name": "default", "price": "19.90", "stock": 10}],
            }
        )

        self.assertIn("images[1].image.path is required", product.validate())

    def test_validates_sku_image_binding(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Test Product",
                "category": "default-category",
                "images": [
                    {"path": "images/main.jpg", "role": "main"},
                    {
                        "path": "images/black.jpg",
                        "role": "sku",
                        "sku_attribute": "颜色分类",
                        "sku_value": "黑色",
                    },
                    {
                        "path": "images/detail.jpg",
                        "role": "detail",
                        "sku_attribute": "颜色分类",
                        "sku_value": "黑色",
                    },
                    {
                        "path": "images/brown.jpg",
                        "role": "sku",
                        "sku_attribute": "颜色分类",
                    },
                ],
                "skus": [{"name": "default", "price": "19.90", "stock": 10}],
            }
        )

        errors = product.validate()
        self.assertIn("images[3].image sku binding is only allowed for sku images", errors)
        self.assertIn("images[4].image sku binding requires both sku_attribute and sku_value", errors)

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

    def test_rejects_reference_price_below_single_price(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Test Product",
                "category": "default-category",
                "images": [{"path": "images/main.jpg", "role": "main"}],
                "skus": [
                    {
                        "name": "42",
                        "price": "29.90",
                        "single_price": "39.90",
                        "reference_price": "39.90",
                        "stock": 10,
                    }
                ],
            }
        )

        self.assertIn("skus[1].sku.reference_price must be greater than single price: 42", product.validate())


if __name__ == "__main__":
    unittest.main()

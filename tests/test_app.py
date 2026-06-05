from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from product_pilot.app import load_single_product_file, validate_product_file


class ProductAppValidationTests(unittest.TestCase):
    def test_validate_product_file_returns_structured_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "main.jpg"
            image_path.write_bytes(b"test")
            product_path = root / "product.json"
            product_path.write_text(
                json.dumps(
                    {
                        "title": "Test Product",
                        "category": "default-category",
                        "images": [{"path": "main.jpg", "role": "main"}],
                        "skus": [{"name": "default", "price": "19.90", "stock": 10}],
                    }
                ),
                encoding="utf-8",
            )

            result = validate_product_file(product_path)

            self.assertTrue(result.ok)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(len(result.products), 1)

    def test_validate_product_file_reports_asset_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_path = Path(tmp) / "product.json"
            product_path.write_text(
                json.dumps(
                    {
                        "title": "Test Product",
                        "category": "default-category",
                        "images": [{"path": "missing.jpg", "role": "main"}],
                        "skus": [{"name": "default", "price": "19.90", "stock": 10}],
                    }
                ),
                encoding="utf-8",
            )

            result = validate_product_file(product_path)

            self.assertFalse(result.ok)
            self.assertEqual(result.exit_code, 1)
            self.assertIn("file not found", result.errors[0])

    def test_load_single_product_file_reports_load_error(self) -> None:
        product, error = load_single_product_file(Path("missing.txt"))

        self.assertIsNone(product)
        self.assertEqual(error, "unsupported product file type: .txt")


if __name__ == "__main__":
    unittest.main()

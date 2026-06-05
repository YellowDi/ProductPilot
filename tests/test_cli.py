from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from product_pilot.cli import validate_product


class ProductCliValidationTests(unittest.TestCase):
    def test_validate_product_resolves_images_from_json_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product_dir = root / "SKU06"
            image_dir = product_dir / "images"
            image_dir.mkdir(parents=True)
            (image_dir / "main.jpg").write_bytes(b"test")
            product_path = product_dir / "product.json"
            product_path.write_text(
                json.dumps(
                    {
                        "title": "Test Product",
                        "category": "default-category",
                        "images": [{"path": "images/main.jpg", "role": "main"}],
                        "skus": [{"name": "default", "price": "19.90", "stock": 10}],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(validate_product(product_path), 0)

    def test_validate_product_rejects_missing_image_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            product_path = Path(tmp) / "product.json"
            product_path.write_text(
                json.dumps(
                    {
                        "title": "Test Product",
                        "category": "default-category",
                        "images": [{"path": "images/main.jpg", "role": "main"}],
                        "skus": [{"name": "default", "price": "19.90", "stock": 10}],
                    }
                ),
                encoding="utf-8",
            )

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(validate_product(product_path), 1)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from decimal import Decimal

from product_pilot.automation.draft import DraftSpikeData, _format_decimal, draft_data_from_product, main_image_from_product
from product_pilot.domain.product import ProductDraft


class DraftSpikeDataTests(unittest.TestCase):
    def test_default_data_is_valid_for_spike(self) -> None:
        data = DraftSpikeData()

        self.assertGreater(data.stock, 0)
        self.assertGreater(data.single_price, data.group_price)
        self.assertGreater(data.reference_price, data.single_price)

    def test_formats_decimal(self) -> None:
        self.assertEqual(_format_decimal(Decimal("29.9")), "29.90")

    def test_maps_product_to_draft_spike_data(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋",
                "category": "流行男鞋 > 低帮鞋 > 板鞋",
                "images": [{"path": "../SKU06.jpg", "role": "main"}],
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

        data = draft_data_from_product(product)

        self.assertEqual(data.title, "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋")
        self.assertEqual(data.size, "42")
        self.assertEqual(data.group_price, Decimal("29.90"))
        self.assertEqual(data.single_price, Decimal("39.90"))
        self.assertEqual(data.reference_price, Decimal("99.00"))
        self.assertEqual(main_image_from_product(product).path.as_posix(), "../SKU06.jpg")


if __name__ == "__main__":
    unittest.main()

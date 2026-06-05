from __future__ import annotations

import unittest
from decimal import Decimal

from product_pilot.automation.draft import (
    DraftSkuData,
    DraftSpikeData,
    _format_decimal,
    draft_data_from_product,
    main_image_from_product,
    sort_skus_for_page,
)
from product_pilot.domain.product import ProductDraft


class DraftSpikeDataTests(unittest.TestCase):
    def test_default_data_is_valid_for_spike(self) -> None:
        data = DraftSpikeData()

        self.assertGreater(data.skus[0].stock, 0)
        self.assertGreater(data.skus[0].single_price, data.skus[0].group_price)
        self.assertGreater(data.reference_price, data.skus[0].single_price)

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
                        "name": "41",
                        "price": "29.90",
                        "single_price": "39.90",
                        "reference_price": "99.00",
                        "stock": 8,
                    },
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
        self.assertEqual([sku.size for sku in data.skus], ["41", "42"])
        self.assertEqual(data.skus[0].group_price, Decimal("29.90"))
        self.assertEqual(data.skus[0].single_price, Decimal("39.90"))
        self.assertEqual(data.reference_price, Decimal("99.00"))
        self.assertEqual(main_image_from_product(product).path.as_posix(), "../SKU06.jpg")

    def test_sorts_numeric_skus_for_page(self) -> None:
        skus = (
            DraftSkuData(size="43", stock=1, group_price=Decimal("1"), single_price=Decimal("2")),
            DraftSkuData(size="41", stock=1, group_price=Decimal("1"), single_price=Decimal("2")),
            DraftSkuData(size="42.5", stock=1, group_price=Decimal("1"), single_price=Decimal("2")),
        )

        self.assertEqual([sku.size for sku in sort_skus_for_page(skus)], ["41", "42.5", "43"])


if __name__ == "__main__":
    unittest.main()

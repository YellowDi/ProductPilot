from __future__ import annotations

import unittest
from decimal import Decimal

from product_pilot.automation.draft import DraftSpikeData, _format_decimal


class DraftSpikeDataTests(unittest.TestCase):
    def test_default_data_is_valid_for_spike(self) -> None:
        data = DraftSpikeData()

        self.assertGreater(data.stock, 0)
        self.assertGreater(data.single_price, data.group_price)
        self.assertGreater(data.reference_price, data.single_price)

    def test_formats_decimal(self) -> None:
        self.assertEqual(_format_decimal(Decimal("29.9")), "29.90")


if __name__ == "__main__":
    unittest.main()


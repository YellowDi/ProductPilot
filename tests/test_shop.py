from __future__ import annotations

import unittest
from pathlib import Path

from product_pilot.domain.shop import format_profile_dir, parse_shop_accounts


class ShopAccountConfigTests(unittest.TestCase):
    def test_parses_shop_account_lines(self) -> None:
        accounts, errors = parse_shop_accounts(
            """
            # name|profile
            店铺A|profiles/shop-a
            店铺B|profiles/shop-b
            """
        )

        self.assertEqual(errors, [])
        self.assertEqual([account.name for account in accounts], ["店铺A", "店铺B"])
        self.assertEqual(accounts[0].profile_dir, Path("profiles/shop-a"))

    def test_reports_invalid_lines_and_duplicates(self) -> None:
        accounts, errors = parse_shop_accounts(
            """
            店铺A
            店铺A|profiles/shop-a
            店铺A|profiles/shop-b
            店铺B|profiles/shop-a
            """
        )

        self.assertEqual(len(accounts), 1)
        self.assertIn("line 2: expected format `店铺名|Profile目录`", errors)
        self.assertIn("line 4: duplicate shop name `店铺A`", errors)
        self.assertIn("line 5: duplicate profile dir `profiles/shop-a`", errors)

    def test_formats_profile_dir_with_posix_separators(self) -> None:
        self.assertEqual(format_profile_dir(Path("profiles") / "shop-a"), "profiles/shop-a")


if __name__ == "__main__":
    unittest.main()

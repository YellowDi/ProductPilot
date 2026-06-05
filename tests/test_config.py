from __future__ import annotations

import unittest
from pathlib import Path

from product_pilot.config import AppConfig


class AppConfigTests(unittest.TestCase):
    def test_valid_config(self) -> None:
        config = AppConfig(
            merchant_backend_url="https://mms.pinduoduo.com/",
            chrome_profile_dir=Path("profiles/chrome"),
            artifacts_dir=Path("artifacts"),
        )

        self.assertEqual(config.validate(), [])

    def test_rejects_invalid_url(self) -> None:
        config = AppConfig(
            merchant_backend_url="mms.pinduoduo.com",
            chrome_profile_dir=Path("profiles/chrome"),
            artifacts_dir=Path("artifacts"),
        )

        self.assertIn("merchant_backend_url must be an http or https URL", config.validate())


if __name__ == "__main__":
    unittest.main()


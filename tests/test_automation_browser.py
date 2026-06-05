from __future__ import annotations

import unittest
from pathlib import Path

from product_pilot.automation.browser import BrowserLaunchConfig


class BrowserLaunchConfigTests(unittest.TestCase):
    def test_valid_browser_config(self) -> None:
        config = BrowserLaunchConfig(
            backend_url="https://mms.pinduoduo.com/",
            user_data_dir=Path("profiles/chrome"),
            artifacts_dir=Path("artifacts/browser"),
        )

        self.assertEqual(config.validate(), [])

    def test_rejects_invalid_timeout(self) -> None:
        config = BrowserLaunchConfig(timeout_ms=0)

        self.assertIn("timeout_ms must be greater than 0", config.validate())

    def test_rejects_invalid_backend_url(self) -> None:
        config = BrowserLaunchConfig(backend_url="mms.pinduoduo.com")

        self.assertIn("backend_url must be an http or https URL", config.validate())


if __name__ == "__main__":
    unittest.main()


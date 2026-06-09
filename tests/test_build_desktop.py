from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_desktop


class BuildDesktopPackageTests(unittest.TestCase):
    def test_windows_archive_root_is_onedir_bundle(self) -> None:
        app_path = Path("release/windows-x64/ProductPilot/ProductPilot.exe")

        with patch("scripts.build_desktop.platform.system", return_value="Windows"):
            self.assertEqual(
                build_desktop.archive_root_for_app(app_path),
                Path("release/windows-x64/ProductPilot"),
            )

    def test_macos_archive_root_is_app_bundle(self) -> None:
        app_path = Path("release/darwin-arm64/ProductPilot.app")

        with patch("scripts.build_desktop.platform.system", return_value="Darwin"):
            self.assertEqual(build_desktop.archive_root_for_app(app_path), app_path)


if __name__ == "__main__":
    unittest.main()

"""Playwright browser session for merchant backend automation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from product_pilot.automation.login import LoginCheckResult, read_login_snapshot, classify_login_snapshot


class BrowserAutomationError(RuntimeError):
    """Raised when the browser automation runtime cannot start or operate."""


@dataclass(frozen=True)
class BrowserLaunchConfig:
    backend_url: str = "https://mms.pinduoduo.com/"
    user_data_dir: Path = Path("profiles/chrome")
    artifacts_dir: Path = Path("artifacts/browser")
    channel: str = "chrome"
    headless: bool = False
    timeout_ms: int = 30_000
    slow_mo_ms: int = 0

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.backend_url.startswith(("http://", "https://")):
            errors.append("backend_url must be an http or https URL")
        if not str(self.user_data_dir):
            errors.append("user_data_dir is required")
        if not str(self.artifacts_dir):
            errors.append("artifacts_dir is required")
        if self.timeout_ms <= 0:
            errors.append("timeout_ms must be greater than 0")
        if self.slow_mo_ms < 0:
            errors.append("slow_mo_ms must be greater than or equal to 0")
        return errors


@dataclass(frozen=True)
class BrowserCheckResult:
    login: LoginCheckResult
    screenshot_path: Path


class PersistentBrowserSession:
    def __init__(self, config: BrowserLaunchConfig) -> None:
        errors = config.validate()
        if errors:
            raise BrowserAutomationError("; ".join(errors))

        self._config = config
        self._playwright: Any | None = None
        self._context: Any | None = None
        self.page: Any | None = None

    def __enter__(self) -> "PersistentBrowserSession":
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise BrowserAutomationError(
                "Playwright is not installed. Install it with `python -m pip install '.[automation]'` "
                "and then run `python -m playwright install chromium`."
            ) from exc

        self._config.user_data_dir.mkdir(parents=True, exist_ok=True)
        self._config.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = sync_playwright().start()
        try:
            launch_kwargs: dict[str, Any] = {
                "user_data_dir": self._config.user_data_dir,
                "headless": self._config.headless,
                "slow_mo": self._config.slow_mo_ms,
                "viewport": {"width": 1440, "height": 1000},
                "accept_downloads": True,
            }
            if self._config.channel and self._config.channel != "bundled":
                launch_kwargs["channel"] = self._config.channel

            self._context = self._playwright.chromium.launch_persistent_context(
                **launch_kwargs,
            )
        except Exception as exc:
            self.close()
            raise BrowserAutomationError(f"failed to launch browser: {exc}") from exc

        try:
            self._context.set_default_timeout(self._config.timeout_ms)
            self.page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self.page.set_default_timeout(self._config.timeout_ms)
        except Exception as exc:
            self.close()
            raise BrowserAutomationError(f"failed to prepare browser page: {exc}") from exc

        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self.page = None

    def open_backend(self) -> None:
        if self.page is None:
            raise BrowserAutomationError("browser session is not started")

        try:
            self.page.goto(self._config.backend_url, wait_until="domcontentloaded")
        except Exception as exc:
            raise BrowserAutomationError(f"failed to open backend url: {exc}") from exc

    def check_login(self) -> BrowserCheckResult:
        if self.page is None:
            raise BrowserAutomationError("browser session is not started")

        try:
            snapshot = read_login_snapshot(self.page)
            login = classify_login_snapshot(snapshot)
            screenshot_path = self.take_screenshot("login-check")
        except BrowserAutomationError:
            raise
        except Exception as exc:
            raise BrowserAutomationError(f"failed to check login state: {exc}") from exc

        return BrowserCheckResult(login=login, screenshot_path=screenshot_path)

    def take_screenshot(self, name: str) -> Path:
        if self.page is None:
            raise BrowserAutomationError("browser session is not started")

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self._config.artifacts_dir / f"{timestamp}-{name}.png"
        try:
            self.page.screenshot(path=path, full_page=True)
        except Exception as exc:
            raise BrowserAutomationError(f"failed to take screenshot: {exc}") from exc
        return path

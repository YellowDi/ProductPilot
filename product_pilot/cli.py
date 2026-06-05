"""Development CLI for ProductPilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from product_pilot.automation.browser import (
    BrowserAutomationError,
    BrowserLaunchConfig,
    PersistentBrowserSession,
)
from product_pilot.automation.login import LoginState
from product_pilot.domain.product import ProductDraft


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="product-pilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a product draft JSON file.")
    validate_parser.add_argument("path", type=Path, help="Path to a product draft JSON file.")

    browser_parser = subparsers.add_parser(
        "browser-check",
        help="Open the merchant backend with a persistent browser profile and check login state.",
    )
    browser_parser.add_argument("--url", default="https://mms.pinduoduo.com/", help="Merchant backend URL.")
    browser_parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path("profiles/chrome"),
        help="Chrome/Chromium user data directory for persistent login state.",
    )
    browser_parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts/browser"),
        help="Directory for screenshots and future trace artifacts.",
    )
    browser_parser.add_argument("--channel", default="chrome", help="Playwright browser channel.")
    browser_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode.")
    browser_parser.add_argument("--timeout-ms", type=int, default=30_000, help="Default Playwright timeout.")
    browser_parser.add_argument("--slow-mo-ms", type=int, default=0, help="Slow down browser actions.")
    browser_parser.add_argument(
        "--hold",
        action="store_true",
        help="Keep the browser open for manual login before checking status.",
    )

    return parser


def validate_product(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"invalid json: {exc}", file=sys.stderr)
        return 2

    product = ProductDraft.from_mapping(payload)
    errors = product.validate()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return validate_product(args.path)
    if args.command == "browser-check":
        return browser_check(args)

    raise AssertionError(f"unsupported command: {args.command}")


def browser_check(args: argparse.Namespace) -> int:
    config = BrowserLaunchConfig(
        backend_url=args.url,
        user_data_dir=args.profile_dir,
        artifacts_dir=args.artifacts_dir,
        channel=args.channel,
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        slow_mo_ms=args.slow_mo_ms,
    )

    try:
        with PersistentBrowserSession(config) as session:
            session.open_backend()
            if args.hold:
                input("Complete manual login in the opened browser, then press Enter to check status...")
            result = session.check_login()
    except BrowserAutomationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"state: {result.login.state.value}")
    print(f"reason: {result.login.reason}")
    print(f"url: {result.login.snapshot.url}")
    print(f"screenshot: {result.screenshot_path.resolve()}")

    if result.login.state == LoginState.LOGGED_IN:
        return 0
    if result.login.state == LoginState.LOGIN_REQUIRED:
        return 1
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

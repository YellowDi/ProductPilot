"""Development CLI for ProductPilot."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from product_pilot.automation.browser import (
    BrowserAutomationError,
    BrowserLaunchConfig,
    PersistentBrowserSession,
)
from product_pilot.automation.category import DEFAULT_CATEGORY_PATH, format_category_path, parse_category_path, select_category
from product_pilot.automation.draft import (
    DraftSpikeData,
    DraftSkuData,
    detect_draft_saved,
    fill_minimal_draft_fields,
    draft_data_from_product,
    images_from_product,
    main_image_from_product,
    save_draft,
    upload_extra_images,
)
from product_pilot.automation.field_scan import scan_publish_fields
from product_pilot.automation.login import LoginState
from product_pilot.automation.publish import PublishPageState
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
    add_browser_arguments(browser_parser, default_url="https://mms.pinduoduo.com/", url_help="Merchant backend URL.")
    browser_parser.add_argument(
        "--hold",
        action="store_true",
        help="Keep the browser open for manual login before checking status.",
    )
    browser_parser.add_argument("--keep-open", action="store_true", help="Keep browser open after printing results.")

    publish_parser = subparsers.add_parser(
        "publish-page-check",
        help="Open the product publish category page and check whether it is ready for automation.",
    )
    add_browser_arguments(
        publish_parser,
        default_url="https://mms.pinduoduo.com/goods/category",
        url_help="Product publish category page URL.",
    )
    publish_parser.add_argument(
        "--hold",
        action="store_true",
        help="Keep the browser open for manual login or risk checks before checking status.",
    )
    publish_parser.add_argument("--keep-open", action="store_true", help="Keep browser open after printing results.")

    field_scan_parser = subparsers.add_parser(
        "field-scan",
        help="Upload a main image, optionally advance to product info, and scan required fields.",
    )
    add_browser_arguments(
        field_scan_parser,
        default_url="https://mms.pinduoduo.com/goods/category",
        url_help="Product publish category page URL.",
    )
    field_scan_parser.add_argument("--main-image", type=Path, required=True, help="Main carousel image to upload.")
    field_scan_parser.add_argument(
        "--category-path",
        default=format_category_path(DEFAULT_CATEGORY_PATH),
        help="Category path to select after image upload.",
    )
    field_scan_parser.add_argument(
        "--advance",
        action="store_true",
        help="Click the next-step button after uploading the main image. This does not save or publish.",
    )
    field_scan_parser.add_argument(
        "--hold",
        action="store_true",
        help="Pause after opening the page for manual login or risk checks before upload.",
    )
    field_scan_parser.add_argument("--keep-open", action="store_true", help="Keep browser open after printing results.")

    draft_parser = subparsers.add_parser(
        "draft-spike",
        help="Upload the test image, select the fixed category, fill minimal fields, and save a draft.",
    )
    add_browser_arguments(
        draft_parser,
        default_url="https://mms.pinduoduo.com/goods/category",
        url_help="Product publish category page URL.",
    )
    draft_parser.add_argument("--product", type=Path, help="Product draft JSON file to use for this run.")
    draft_parser.add_argument("--main-image", type=Path, help="Main carousel image to upload.")
    draft_parser.add_argument(
        "--category-path",
        help="Category path to select after image upload. Defaults to product.category or the fixed test category.",
    )
    draft_parser.add_argument("--title", help="Product title for the draft spike.")
    draft_parser.add_argument("--size", help="Single shoe size to enable.")
    draft_parser.add_argument("--stock", type=int, help="Stock for the enabled SKU.")
    draft_parser.add_argument("--group-price", help="Pinduoduo group price.")
    draft_parser.add_argument("--single-price", help="Single-buy price.")
    draft_parser.add_argument(
        "--reference-price",
        help="Reference price greater than the single-buy price.",
    )
    draft_parser.add_argument(
        "--hold",
        action="store_true",
        help="Pause after opening the page for manual login or risk checks before upload.",
    )
    draft_parser.add_argument("--no-save", action="store_true", help="Fill fields but do not click save draft.")
    draft_parser.add_argument("--keep-open", action="store_true", help="Keep browser open after printing results.")

    return parser


def add_browser_arguments(parser: argparse.ArgumentParser, *, default_url: str, url_help: str) -> None:
    parser.add_argument("--url", default=default_url, help=url_help)
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path("profiles/chrome"),
        help="Chrome/Chromium user data directory for persistent login state.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("artifacts/browser"),
        help="Directory for screenshots and future trace artifacts.",
    )
    parser.add_argument("--channel", default="chrome", help="Playwright browser channel.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode.")
    parser.add_argument("--timeout-ms", type=int, default=30_000, help="Default Playwright timeout.")
    parser.add_argument("--slow-mo-ms", type=int, default=0, help="Slow down browser actions.")


def validate_product(path: Path) -> int:
    product = load_product_file(path)
    if product is None:
        return 2

    errors = product.validate()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("ok")
    return 0


def load_product_file(path: Path) -> ProductDraft | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"file not found: {path}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"invalid json: {exc}", file=sys.stderr)
        return None

    return ProductDraft.from_mapping(payload)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return validate_product(args.path)
    if args.command == "browser-check":
        return browser_check(args)
    if args.command == "publish-page-check":
        return publish_page_check(args)
    if args.command == "field-scan":
        return field_scan(args)
    if args.command == "draft-spike":
        return draft_spike(args)

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
                wait_for_user("Complete manual login in the opened browser, then press Enter to check status...")
            result = session.check_login()
            if args.keep_open:
                wait_for_user("Press Enter to close the browser...")
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


def publish_page_check(args: argparse.Namespace) -> int:
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
                wait_for_user("Complete manual login or risk checks in the opened browser, then press Enter...")
            result = session.check_publish_page()
            if args.keep_open:
                wait_for_user("Press Enter to close the browser...")
    except BrowserAutomationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"state: {result.publish_page.state.value}")
    print(f"reason: {result.publish_page.reason}")
    print(f"url: {result.publish_page.snapshot.url}")
    print(f"screenshot: {result.screenshot_path.resolve()}")

    if result.publish_page.state == PublishPageState.READY:
        return 0
    if result.publish_page.state in {
        PublishPageState.LOGIN_REQUIRED,
        PublishPageState.RISK_CHECK_REQUIRED,
    }:
        return 1
    return 3


def field_scan(args: argparse.Namespace) -> int:
    main_image = args.main_image.resolve()
    if not main_image.exists():
        print(f"main image not found: {main_image}", file=sys.stderr)
        return 2

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
                wait_for_user("Complete manual login or risk checks in the opened browser, then press Enter...")

            page_check = session.check_publish_page()
            if page_check.publish_page.state != PublishPageState.READY:
                print(f"state: {page_check.publish_page.state.value}")
                print(f"reason: {page_check.publish_page.reason}")
                print(f"url: {page_check.publish_page.snapshot.url}")
                print(f"screenshot: {page_check.screenshot_path.resolve()}")
                if args.keep_open:
                    wait_for_user("Press Enter to close the browser...")
                return 1

            notes: list[str] = []
            session.page.locator("input[type=file]").first.set_input_files(str(main_image))
            session.wait(12_000)

            category_path = parse_category_path(args.category_path)
            if category_path:
                try:
                    category_result = select_category(session.page, category_path)
                except Exception as exc:
                    notes.append(f"category selection failed: {exc}")
                    category_selected = False
                else:
                    category_selected = True
                    notes.extend(category_result.notes)
                    session.wait(2_000)
            else:
                category_selected = True

            if args.advance and category_selected:
                try:
                    session.page.get_by_text("下一步, 完善商品信息", exact=True).click(timeout=8_000)
                except Exception as exc:
                    notes.append(f"advance failed: {exc}")
                else:
                    notes.append("advanced to product info page")
                session.wait(8_000)
            elif args.advance:
                notes.append("advance skipped because category selection failed")

            screenshot_path = session.take_screenshot("field-scan")
            result = scan_publish_fields(session.page, screenshot_path, notes=notes)
            output_path = result.screenshot_path.with_suffix(".json")
            output_path.write_text(
                json.dumps(result.to_mapping(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            print_field_scan_result(result, output_path)
            if args.keep_open:
                wait_for_user("Press Enter to close the browser...")
    except BrowserAutomationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0


def print_field_scan_result(result: Any, output_path: Path) -> None:
    print(f"url: {result.url}")
    print(f"title: {result.title}")
    print(f"required_labels: {', '.join(result.required_labels) if result.required_labels else '<none>'}")
    print(f"fields: {len(result.fields)}")
    print(f"actions: {len(result.actions)}")
    if result.notes:
        print("notes:")
        for note in result.notes:
            print(f"- {note.splitlines()[0]}")
    print(f"screenshot: {result.screenshot_path.resolve()}")
    print(f"json: {output_path.resolve()}")


def draft_spike(args: argparse.Namespace) -> int:
    default_draft = DraftSpikeData()
    product_base_dir = Path.cwd()
    product = None
    if args.product is not None:
        product = load_product_file(args.product)
        if product is None:
            return 2
        errors = product.validate()
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        product_base_dir = args.product.resolve().parent
        default_draft = draft_data_from_product(product)

    if args.main_image is not None:
        main_image = args.main_image
    elif product is not None:
        main_image = product_base_dir / main_image_from_product(product).path
    else:
        print("main image is required unless --product is provided", file=sys.stderr)
        return 2

    main_image = main_image.resolve()
    if not main_image.exists():
        print(f"main image not found: {main_image}", file=sys.stderr)
        return 2
    detail_images: tuple[Path, ...] = ()
    sku_image: Path | None = None
    if product is not None:
        detail_images = tuple(
            (product_base_dir / image.path).resolve()
            for image in images_from_product(product, "detail")
        )
        sku_images = tuple(
            (product_base_dir / image.path).resolve()
            for image in images_from_product(product, "sku")
        )
        sku_image = sku_images[0] if sku_images else None
        missing_images = [path for path in (*detail_images, *(sku_images[:1])) if not path.exists()]
        if missing_images:
            for path in missing_images:
                print(f"image not found: {path}", file=sys.stderr)
            return 2

    config = BrowserLaunchConfig(
        backend_url=args.url,
        user_data_dir=args.profile_dir,
        artifacts_dir=args.artifacts_dir,
        channel=args.channel,
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        slow_mo_ms=args.slow_mo_ms,
    )
    data = DraftSpikeData(
        title=args.title or default_draft.title,
        skus=_resolve_draft_skus(args, default_draft),
        reference_price=Decimal(
            str(args.reference_price if args.reference_price is not None else default_draft.reference_price)
        ),
    )

    try:
        with PersistentBrowserSession(config) as session:
            session.open_backend()
            if args.hold:
                wait_for_user("Complete manual login or risk checks in the opened browser, then press Enter...")

            page_check = session.check_publish_page()
            if page_check.publish_page.state != PublishPageState.READY:
                print(f"state: {page_check.publish_page.state.value}")
                print(f"reason: {page_check.publish_page.reason}")
                print(f"url: {page_check.publish_page.snapshot.url}")
                print(f"screenshot: {page_check.screenshot_path.resolve()}")
                if args.keep_open:
                    wait_for_user("Press Enter to close the browser...")
                return 1

            notes: list[str] = []
            session.page.locator("input[type=file]").first.set_input_files(str(main_image))
            session.wait(10_000)

            category_value = args.category_path
            if category_value is None and product is not None:
                category_value = product.category
            if category_value is None:
                category_value = format_category_path(DEFAULT_CATEGORY_PATH)
            category_path = parse_category_path(category_value)
            category_result = select_category(session.page, category_path)
            notes.extend(category_result.notes)
            session.wait(2_000)

            session.page.get_by_text("下一步, 完善商品信息", exact=True).click(timeout=10_000)
            session.wait(8_000)

            notes.extend(fill_minimal_draft_fields(session.page, data))
            upload_notes, upload_targets = upload_extra_images(
                session.page,
                detail_images=detail_images,
                sku_image=sku_image,
            )
            notes.extend(upload_notes)
            if args.no_save:
                notes.append("save skipped by --no-save")
                saved = False
            else:
                notes.extend(save_draft(session.page))
                saved = detect_draft_saved(session.page)
            screenshot_path = session.take_screenshot("draft-spike")
            output_path = screenshot_path.with_suffix(".json")
            output_path.write_text(
                json.dumps(
                    {
                        "url": session.page.url,
                        "saved": saved,
                        "no_save": args.no_save,
                        "notes": notes,
                        "upload_targets": [target.to_mapping() for target in upload_targets],
                        "screenshot_path": str(screenshot_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            print(f"saved: {saved}")
            print(f"url: {session.page.url}")
            print("notes:")
            for note in notes:
                print(f"- {note.splitlines()[0]}")
            print(f"screenshot: {screenshot_path.resolve()}")
            print(f"json: {output_path.resolve()}")
            if args.keep_open:
                wait_for_user("Press Enter to close the browser...")
    except BrowserAutomationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0 if saved or args.no_save else 1


def _resolve_draft_skus(args: argparse.Namespace, default_draft: DraftSpikeData) -> tuple[DraftSkuData, ...]:
    if any(value is not None for value in (args.size, args.stock, args.group_price, args.single_price)):
        first_sku = default_draft.skus[0]
        return (
            DraftSkuData(
                size=args.size or first_sku.size,
                stock=args.stock if args.stock is not None else first_sku.stock,
                group_price=Decimal(str(args.group_price if args.group_price is not None else first_sku.group_price)),
                single_price=Decimal(
                    str(args.single_price if args.single_price is not None else first_sku.single_price)
                ),
            ),
        )

    return default_draft.skus


def wait_for_user(prompt: str) -> None:
    try:
        input(prompt)
    except EOFError:
        return


if __name__ == "__main__":
    raise SystemExit(main())

"""Development CLI for ProductPilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from product_pilot.automation.browser import (
    BrowserAutomationError,
    BrowserLaunchConfig,
    PersistentBrowserSession,
)
from product_pilot.automation.category import (
    DEFAULT_CATEGORY_PATH,
    click_next_product_info,
    format_category_path,
    parse_category_path,
    select_category,
)
from product_pilot.automation.field_scan import scan_publish_fields
from product_pilot.automation.publish import PublishPageState
from product_pilot.app import (
    DraftSpikePageNotReadyError,
    DraftSpikeRequest,
    ProductPilotAppError,
    browser_login_exit_code,
    load_single_product_file,
    load_products_file as load_products_file_result,
    publish_page_exit_code,
    run_browser_login_check,
    run_draft_spike,
    run_publish_page_check,
    validate_product_file,
)
from product_pilot.domain.product import ProductDraft
from product_pilot.importers.zzb import (
    ZzbImportError,
    ZzbImportRequest,
    import_zzb_export,
    suggest_zzb_output_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="product-pilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a product draft JSON or XLSX file.")
    validate_parser.add_argument("path", type=Path, help="Path to a product draft JSON or XLSX file.")

    import_zzb_parser = subparsers.add_parser(
        "import-zzb",
        help="Convert a Zhizunbao export into ProductPilot's standard product-input.xlsx format.",
    )
    import_zzb_parser.add_argument("--excel", type=Path, required=True, help="Zhizunbao exported XLSX file.")
    import_zzb_parser.add_argument("--assets", type=Path, required=True, help="Zhizunbao media zip or extracted folder.")
    import_zzb_parser.add_argument("--sku-text-file", type=Path, help="Text file containing copied Zhizunbao SKU text.")
    import_zzb_parser.add_argument("--sku-text", help="Copied Zhizunbao SKU text.")
    import_zzb_parser.add_argument("--title", required=True, help="Product title for the generated workbook.")
    import_zzb_parser.add_argument("--category", required=True, help="Product category path for the generated workbook.")
    import_zzb_parser.add_argument("--product-id", default="", help="Product id. Defaults to 商品ID parsed from media path.")
    import_zzb_parser.add_argument("--product-code", default="", help="Product code. Defaults to product id.")
    import_zzb_parser.add_argument(
        "--output",
        type=Path,
        help="Generated ProductPilot XLSX path. Defaults to imports/<product-id>/product-input.xlsx.",
    )

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
    result = validate_product_file(path)
    if result.load_error:
        print(result.load_error, file=sys.stderr)
        return result.exit_code

    if result.errors:
        for error in result.errors:
            print(error, file=sys.stderr)
        return result.exit_code

    print("ok")
    return result.exit_code


def load_products_file(path: Path) -> list[ProductDraft] | None:
    products, error = load_products_file_result(path)
    if error:
        print(error, file=sys.stderr)
        return None
    return products


def load_product_file(path: Path) -> ProductDraft | None:
    product, error = load_single_product_file(path)
    if error:
        print(error, file=sys.stderr)
        return None
    return product


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return validate_product(args.path)
    if args.command == "import-zzb":
        return import_zzb(args)
    if args.command == "browser-check":
        return browser_check(args)
    if args.command == "publish-page-check":
        return publish_page_check(args)
    if args.command == "field-scan":
        return field_scan(args)
    if args.command == "draft-spike":
        return draft_spike(args)

    raise AssertionError(f"unsupported command: {args.command}")


def import_zzb(args: argparse.Namespace) -> int:
    sku_text = args.sku_text or ""
    if args.sku_text_file is not None:
        try:
            sku_text = args.sku_text_file.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"failed to read SKU text file: {exc}", file=sys.stderr)
            return 2
    if not sku_text.strip():
        print("--sku-text or --sku-text-file is required", file=sys.stderr)
        return 2

    output_path = args.output or suggest_zzb_output_path(Path("imports"), args.excel, args.assets)
    try:
        result = import_zzb_export(
            ZzbImportRequest(
                excel_path=args.excel,
                sku_text=sku_text,
                assets_path=args.assets,
                title=args.title,
                category=args.category,
                product_id=args.product_id,
                product_code=args.product_code,
                output_path=output_path,
            )
        )
    except ZzbImportError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"output: {result.output_path.resolve()}")
    print(f"asset_root: {result.asset_root.resolve()}")
    print(f"skus: {len(result.product.skus)}")
    print(f"images: {len(result.product.images)}")
    for note in result.notes:
        print(f"note: {note}")
    return 0


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
        result = run_browser_login_check(
            config,
            hold_callback=wait_for_user if args.hold else None,
            keep_open_callback=wait_for_user if args.keep_open else None,
        )
    except BrowserAutomationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"state: {result.login.state.value}")
    print(f"reason: {result.login.reason}")
    print(f"url: {result.login.snapshot.url}")
    print(f"screenshot: {result.screenshot_path.resolve()}")

    return browser_login_exit_code(result)


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
        result = run_publish_page_check(
            config,
            hold_callback=wait_for_user if args.hold else None,
            keep_open_callback=wait_for_user if args.keep_open else None,
        )
    except BrowserAutomationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"state: {result.publish_page.state.value}")
    print(f"reason: {result.publish_page.reason}")
    print(f"url: {result.publish_page.snapshot.url}")
    print(f"screenshot: {result.screenshot_path.resolve()}")

    return publish_page_exit_code(result)


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
                    click_next_product_info(session.page, notes, timeout=8_000)
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
    config = BrowserLaunchConfig(
        backend_url=args.url,
        user_data_dir=args.profile_dir,
        artifacts_dir=args.artifacts_dir,
        channel=args.channel,
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        slow_mo_ms=args.slow_mo_ms,
    )
    request = DraftSpikeRequest(
        product_path=args.product,
        main_image=args.main_image,
        category_path=args.category_path,
        title=args.title,
        size=args.size,
        stock=args.stock,
        group_price=args.group_price,
        single_price=args.single_price,
        reference_price=args.reference_price,
        no_save=args.no_save,
    )

    try:
        result = run_draft_spike(
            config,
            request,
            hold_callback=wait_for_user if args.hold else None,
            keep_open_callback=wait_for_user if args.keep_open else None,
        )
    except DraftSpikePageNotReadyError as exc:
        print(f"state: {exc.state.value}")
        print(f"reason: {exc.reason}")
        print(f"url: {exc.url}")
        print(f"screenshot: {exc.screenshot_path.resolve()}")
        return exc.exit_code
    except ProductPilotAppError as exc:
        print(str(exc), file=sys.stderr)
        if exc.screenshot_path is not None:
            print(f"screenshot: {exc.screenshot_path.resolve()}")
        return exc.exit_code
    except BrowserAutomationError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"saved: {result.saved}")
    print(f"url: {result.url}")
    print("notes:")
    for note in result.notes:
        print(f"- {note.splitlines()[0]}")
    print(f"screenshot: {result.screenshot_path.resolve()}")
    print(f"json: {result.output_path.resolve()}")
    return result.exit_code


def wait_for_user(prompt: str) -> None:
    try:
        input(prompt)
    except EOFError:
        return


if __name__ == "__main__":
    raise SystemExit(main())

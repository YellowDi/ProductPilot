"""Application-level operations shared by the CLI and desktop UI."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from product_pilot.automation.browser import (
    BrowserAutomationError,
    BrowserCheckResult,
    BrowserLaunchConfig,
    PersistentBrowserSession,
    PublishPageBrowserCheckResult,
)
from product_pilot.automation.category import (
    DEFAULT_CATEGORY_PATH,
    click_next_product_info,
    format_category_path,
    parse_category_path,
    select_category,
)
from product_pilot.automation.draft import (
    DraftSkuData,
    DraftSpikeData,
    SkuImageUpload,
    UploadTarget,
    detect_draft_saved,
    draft_data_from_product,
    fill_minimal_draft_fields,
    images_from_product,
    main_image_from_product,
    save_draft,
    upload_extra_images,
    wait_for_uploads_to_settle,
)
from product_pilot.automation.login import LoginState
from product_pilot.automation.publish import RISK_CHECK_MARKERS, PublishPageState
from product_pilot.domain.product import ProductDraft
from product_pilot.importers.xlsx import ProductWorkbookError, load_products_from_xlsx

WaitCallback = Callable[[str], None]


@dataclass(frozen=True)
class ProductValidationResult:
    path: Path
    products: tuple[ProductDraft, ...]
    errors: tuple[str, ...] = ()
    load_error: str = ""

    @property
    def ok(self) -> bool:
        return not self.load_error and not self.errors

    @property
    def exit_code(self) -> int:
        if self.load_error:
            return 2
        if self.errors:
            return 1
        return 0


@dataclass(frozen=True)
class DraftSpikeRequest:
    product_path: Path | None = None
    main_image: Path | None = None
    category_path: str | None = None
    title: str | None = None
    size: str | None = None
    stock: int | None = None
    group_price: str | None = None
    single_price: str | None = None
    reference_price: str | None = None
    no_save: bool = False


@dataclass(frozen=True)
class DraftSpikeRunResult:
    url: str
    saved: bool
    no_save: bool
    notes: tuple[str, ...]
    upload_targets: tuple[UploadTarget, ...]
    screenshot_path: Path
    output_path: Path

    @property
    def exit_code(self) -> int:
        return 0 if self.saved or self.no_save else 1


@dataclass(frozen=True)
class _PreparedDraftSpike:
    main_image: Path
    category_value: str
    data: DraftSpikeData
    extra_main_images: tuple[Path, ...]
    detail_images: tuple[Path, ...]
    sku_images: tuple[SkuImageUpload, ...]


class ProductPilotAppError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        exit_code: int = 1,
        screenshot_path: Path | None = None,
    ) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.screenshot_path = screenshot_path


class DraftSpikePageNotReadyError(ProductPilotAppError):
    def __init__(
        self,
        *,
        state: PublishPageState,
        reason: str,
        url: str,
        screenshot_path: Path,
    ) -> None:
        super().__init__(reason, exit_code=1, screenshot_path=screenshot_path)
        self.state = state
        self.reason = reason
        self.url = url


def validate_product_file(path: Path) -> ProductValidationResult:
    products, load_error = load_products_file(path)
    if load_error:
        return ProductValidationResult(path=path, products=(), load_error=load_error)

    base_dir = path.resolve().parent
    return ProductValidationResult(
        path=path,
        products=tuple(products),
        errors=tuple(validate_loaded_products(products, base_dir)),
    )


def load_products_file(path: Path) -> tuple[list[ProductDraft], str]:
    if path.suffix.lower() == ".xlsx":
        try:
            return load_products_from_xlsx(path), ""
        except ProductWorkbookError as exc:
            return [], str(exc)
    if path.suffix.lower() != ".json":
        return [], f"unsupported product file type: {path.suffix or '<none>'}"

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], f"file not found: {path}"
    except json.JSONDecodeError as exc:
        return [], f"invalid json: {exc}"

    return [ProductDraft.from_mapping(payload)], ""


def load_single_product_file(path: Path) -> tuple[ProductDraft | None, str]:
    products, error = load_products_file(path)
    if error:
        return None, error
    if len(products) != 1:
        return None, f"expected exactly one product, found {len(products)}"
    return products[0], ""


def validate_loaded_products(products: list[ProductDraft], base_dir: Path) -> list[str]:
    errors: list[str] = []
    for index, product in enumerate(products, start=1):
        product_errors = product.validate()
        product_errors.extend(validate_product_assets(product, base_dir))
        if len(products) == 1:
            errors.extend(product_errors)
        else:
            label = product.product_id or str(index)
            errors.extend(f"products[{label}].{error}" for error in product_errors)
    return errors


def validate_product_assets(product: ProductDraft, base_dir: Path) -> list[str]:
    errors: list[str] = []
    for index, image in enumerate(product.images, start=1):
        if str(image.path) in {"", "."}:
            continue
        image_path = resolve_product_asset_path(base_dir, image.path)
        if not image_path.exists():
            errors.append(f"images[{index}].image.path file not found: {image_path}")
        elif not image_path.is_file():
            errors.append(f"images[{index}].image.path is not a file: {image_path}")
    return errors


def resolve_product_asset_path(base_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def run_browser_login_check(
    config: BrowserLaunchConfig,
    *,
    hold_callback: WaitCallback | None = None,
    keep_open_callback: WaitCallback | None = None,
) -> BrowserCheckResult:
    try:
        with PersistentBrowserSession(config) as session:
            session.open_backend()
            if hold_callback is not None:
                hold_callback("Complete manual login in the opened browser, then press Enter to check status...")
            result = session.check_login()
            if keep_open_callback is not None:
                keep_open_callback("Press Enter to close the browser...")
            return result
    except BrowserAutomationError:
        raise


def browser_login_exit_code(result: BrowserCheckResult) -> int:
    if result.login.state == LoginState.LOGGED_IN:
        return 0
    if result.login.state == LoginState.LOGIN_REQUIRED:
        return 1
    return 3


def run_publish_page_check(
    config: BrowserLaunchConfig,
    *,
    hold_callback: WaitCallback | None = None,
    keep_open_callback: WaitCallback | None = None,
) -> PublishPageBrowserCheckResult:
    try:
        with PersistentBrowserSession(config) as session:
            session.open_backend()
            if hold_callback is not None:
                hold_callback("Complete manual login or risk checks in the opened browser, then press Enter...")
            result = session.check_publish_page()
            if keep_open_callback is not None:
                keep_open_callback("Press Enter to close the browser...")
            return result
    except BrowserAutomationError:
        raise


def publish_page_exit_code(result: PublishPageBrowserCheckResult) -> int:
    if result.publish_page.state == PublishPageState.READY:
        return 0
    if result.publish_page.state in {
        PublishPageState.LOGIN_REQUIRED,
        PublishPageState.RISK_CHECK_REQUIRED,
    }:
        return 1
    return 3


def run_draft_spike(
    config: BrowserLaunchConfig,
    request: DraftSpikeRequest,
    *,
    hold_callback: WaitCallback | None = None,
    manual_check_callback: WaitCallback | None = None,
    keep_open_callback: WaitCallback | None = None,
) -> DraftSpikeRunResult:
    prepared = _prepare_draft_spike_request(request)

    try:
        session = PersistentBrowserSession(config).__enter__()
        try:
            session.open_backend()
            if hold_callback is not None:
                hold_callback("Complete manual login or risk checks in the opened browser, then press Enter...")

            page_check = _wait_for_publish_page_ready(session, manual_check_callback)
            if page_check.publish_page.state != PublishPageState.READY:
                if keep_open_callback is not None:
                    keep_open_callback("Press Enter to close the browser...")
                raise DraftSpikePageNotReadyError(
                    state=page_check.publish_page.state,
                    reason=page_check.publish_page.reason,
                    url=page_check.publish_page.snapshot.url,
                    screenshot_path=page_check.screenshot_path,
                )

            notes: list[str] = []
            _pause_for_manual_check_if_present(session.page, manual_check_callback, notes, "上传主图前")
            _run_with_manual_check_retry(
                "上传主图",
                session.page,
                manual_check_callback,
                notes,
                lambda: (
                    session.page.locator("input[type=file]").first.set_input_files(str(prepared.main_image)),
                    wait_for_uploads_to_settle(session.page),
                ),
            )
            _pause_for_manual_check_if_present(session.page, manual_check_callback, notes, "上传主图后")

            category_path = parse_category_path(prepared.category_value)
            category_result = _run_with_manual_check_retry(
                "选择类目",
                session.page,
                manual_check_callback,
                notes,
                lambda: select_category(session.page, category_path),
            )
            notes.extend(category_result.notes)
            session.wait(2_000)
            _pause_for_manual_check_if_present(session.page, manual_check_callback, notes, "选择类目后")

            _run_with_manual_check_retry(
                "进入商品信息页",
                session.page,
                manual_check_callback,
                notes,
                lambda: click_next_product_info(session.page, notes, timeout=10_000),
            )
            session.wait(8_000)
            _pause_for_manual_check_if_present(session.page, manual_check_callback, notes, "进入商品信息页后")

            notes.extend(
                _run_with_manual_check_retry(
                    "填写商品信息",
                    session.page,
                    manual_check_callback,
                    notes,
                    lambda: fill_minimal_draft_fields(
                        session.page,
                        prepared.data,
                        sku_images=prepared.sku_images,
                    ),
                )
            )
            _pause_for_manual_check_if_present(session.page, manual_check_callback, notes, "填写商品信息后")
            upload_notes, upload_targets = _run_with_manual_check_retry(
                "上传附加图片",
                session.page,
                manual_check_callback,
                notes,
                lambda: upload_extra_images(
                    session.page,
                    main_images=prepared.extra_main_images,
                    detail_images=prepared.detail_images,
                    sku_images=tuple(
                        image.path
                        for image in prepared.sku_images
                        if image.sku_attribute != "颜色分类"
                    ),
                ),
            )
            notes.extend(upload_notes)
            _pause_for_manual_check_if_present(session.page, manual_check_callback, notes, "上传附加图片后")
            if request.no_save:
                notes.append("save skipped by --no-save")
                saved = False
            else:
                _pause_for_manual_check_if_present(session.page, manual_check_callback, notes, "保存草稿前")
                notes.extend(
                    _run_with_manual_check_retry(
                        "保存草稿",
                        session.page,
                        manual_check_callback,
                        notes,
                        lambda: save_draft(session.page),
                    )
                )
                _pause_for_manual_check_if_present(session.page, manual_check_callback, notes, "保存草稿后")
                saved = detect_draft_saved(session.page)

            screenshot_path = session.take_screenshot("draft-spike")
            output_path = screenshot_path.with_suffix(".json")
            output_path.write_text(
                json.dumps(
                    {
                        "url": session.page.url,
                        "saved": saved,
                        "no_save": request.no_save,
                        "notes": notes,
                        "upload_targets": [target.to_mapping() for target in upload_targets],
                        "screenshot_path": str(screenshot_path),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            if keep_open_callback is not None:
                keep_open_callback("Press Enter to close the browser...")

            return DraftSpikeRunResult(
                url=session.page.url,
                saved=saved,
                no_save=request.no_save,
                notes=tuple(notes),
                upload_targets=tuple(upload_targets),
                screenshot_path=screenshot_path,
                output_path=output_path,
            )
        except ProductPilotAppError:
            raise
        except BrowserAutomationError:
            raise
        except Exception as exc:
            screenshot_path: Path | None = None
            try:
                screenshot_path = session.take_screenshot("draft-spike-error")
            except Exception:
                screenshot_path = None
            if keep_open_callback is not None:
                keep_open_callback(
                    "Automation stopped. If a verification is visible, handle it in the browser, "
                    "then press Enter to close the browser..."
                )
            raise ProductPilotAppError(
                f"draft spike failed: {exc}",
                exit_code=1,
                screenshot_path=screenshot_path,
            ) from exc
        finally:
            session.close()
    except BrowserAutomationError:
        raise


def _wait_for_publish_page_ready(
    session: PersistentBrowserSession,
    manual_check_callback: WaitCallback | None,
) -> PublishPageBrowserCheckResult:
    result = session.check_publish_page()
    attempts = 0
    while (
        result.publish_page.state in {PublishPageState.LOGIN_REQUIRED, PublishPageState.RISK_CHECK_REQUIRED}
        and manual_check_callback is not None
        and attempts < 20
    ):
        attempts += 1
        manual_check_callback(
            "拼多多页面需要人工处理登录或人机验证。"
            "请在打开的 Chrome 中完成处理，确认页面回到发布商品流程后再继续。"
        )
        session.wait(2_000)
        result = session.check_publish_page()
    return result


def _pause_for_manual_check_if_present(
    page: object,
    manual_check_callback: WaitCallback | None,
    notes: list[str],
    step: str,
) -> None:
    if manual_check_callback is None:
        return

    attempts = 0
    while _page_has_manual_check(page) and attempts < 20:
        attempts += 1
        notes.append(f"manual verification paused at: {step}")
        manual_check_callback(
            f"检测到拼多多人机验证：{step}。"
            "请在打开的 Chrome 中完成人机验证，页面恢复后再继续。"
        )
        try:
            page.wait_for_timeout(1_000)
        except Exception:
            return


def _run_with_manual_check_retry(
    step: str,
    page: object,
    manual_check_callback: WaitCallback | None,
    notes: list[str],
    action: Callable[[], object],
) -> object:
    for attempt in range(3):
        _pause_for_manual_check_if_present(page, manual_check_callback, notes, f"{step}前")
        try:
            return action()
        except Exception:
            if manual_check_callback is None or attempt == 2 or not _page_has_manual_check(page):
                raise
            notes.append(f"manual verification interrupted step: {step}")
            manual_check_callback(
                f"执行“{step}”时检测到拼多多人机验证。"
                "请在打开的 Chrome 中完成人机验证，页面恢复后再继续。"
            )
            try:
                page.wait_for_timeout(1_000)
            except Exception:
                raise

    raise AssertionError("unreachable manual check retry state")


def _page_has_manual_check(page: object) -> bool:
    try:
        text = str(page.locator("body").inner_text(timeout=2_000))
    except Exception:
        return False

    extra_markers = (
        "安全验证",
        "人机验证",
        "请完成验证",
        "拖动滑块",
        "验证码",
    )
    return any(marker in text for marker in (*RISK_CHECK_MARKERS, *extra_markers))


def _prepare_draft_spike_request(request: DraftSpikeRequest) -> _PreparedDraftSpike:
    default_draft = DraftSpikeData()
    product_base_dir = Path.cwd()
    product = None
    if request.product_path is not None:
        product, error = load_single_product_file(request.product_path)
        if error:
            raise ProductPilotAppError(error, exit_code=2)
        assert product is not None
        errors = product.validate()
        if errors:
            raise ProductPilotAppError("\n".join(errors), exit_code=1)
        product_base_dir = request.product_path.resolve().parent
        asset_errors = validate_product_assets(product, product_base_dir)
        if asset_errors:
            raise ProductPilotAppError("\n".join(asset_errors), exit_code=2)
        default_draft = draft_data_from_product(product)

    if request.main_image is not None:
        main_image = request.main_image
    elif product is not None:
        main_image = resolve_product_asset_path(product_base_dir, main_image_from_product(product).path)
    else:
        raise ProductPilotAppError("main image is required unless --product is provided", exit_code=2)

    main_image = main_image.resolve()
    if not main_image.exists():
        raise ProductPilotAppError(f"main image not found: {main_image}", exit_code=2)

    extra_main_images: tuple[Path, ...] = ()
    detail_images: tuple[Path, ...] = ()
    sku_images: tuple[SkuImageUpload, ...] = ()
    if product is not None:
        product_main_images = tuple(
            resolve_product_asset_path(product_base_dir, image.path)
            for image in images_from_product(product, "main")
        )
        extra_main_images = tuple(path for path in product_main_images if path != main_image)
        detail_images = tuple(
            resolve_product_asset_path(product_base_dir, image.path)
            for image in images_from_product(product, "detail")
        )
        sku_images = tuple(
            SkuImageUpload(
                path=resolve_product_asset_path(product_base_dir, image.path),
                sku_attribute=image.sku_attribute,
                sku_value=image.sku_value,
            )
            for image in images_from_product(product, "sku")
        )

    category_value = request.category_path
    if category_value is None and product is not None:
        category_value = product.category
    if category_value is None:
        category_value = format_category_path(DEFAULT_CATEGORY_PATH)

    data = DraftSpikeData(
        title=request.title or default_draft.title,
        skus=_resolve_draft_skus(request, default_draft),
        reference_price=Decimal(
            str(request.reference_price if request.reference_price is not None else default_draft.reference_price)
        ),
        product_code=default_draft.product_code,
    )

    return _PreparedDraftSpike(
        main_image=main_image,
        category_value=category_value,
        data=data,
        extra_main_images=extra_main_images,
        detail_images=detail_images,
        sku_images=sku_images,
    )


def _resolve_draft_skus(
    request: DraftSpikeRequest,
    default_draft: DraftSpikeData,
) -> tuple[DraftSkuData, ...]:
    if any(
        value is not None
        for value in (
            request.size,
            request.stock,
            request.group_price,
            request.single_price,
        )
    ):
        first_sku = default_draft.skus[0]
        return (
            DraftSkuData(
                size=request.size or first_sku.size,
                stock=request.stock if request.stock is not None else first_sku.stock,
                group_price=Decimal(
                    str(request.group_price if request.group_price is not None else first_sku.group_price)
                ),
                single_price=Decimal(
                    str(request.single_price if request.single_price is not None else first_sku.single_price)
                ),
            ),
        )

    return default_draft.skus

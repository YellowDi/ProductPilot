"""Minimal draft filling helpers for the product publish spike."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from product_pilot.domain.product import ProductDraft, ProductImage, ProductSku


@dataclass(frozen=True)
class DraftSkuData:
    size: str = "42"
    stock: int = 10
    group_price: Decimal = Decimal("29.90")
    single_price: Decimal = Decimal("39.90")
    option_values: tuple[str, ...] = ()
    attribute_values: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class SkuOptionGroup:
    attribute: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class SkuImageUpload:
    path: Path
    sku_attribute: str = ""
    sku_value: str = ""


@dataclass(frozen=True)
class DraftSpikeData:
    title: str = "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋"
    skus: tuple[DraftSkuData, ...] = (DraftSkuData(),)
    reference_price: Decimal = Decimal("99.00")
    product_code: str = ""


@dataclass(frozen=True)
class DraftSpikeResult:
    url: str
    saved: bool
    notes: list[str]
    screenshot_path: Path

    def to_mapping(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "saved": self.saved,
            "notes": self.notes,
            "screenshot_path": str(self.screenshot_path),
        }


@dataclass(frozen=True)
class UploadTarget:
    file_input_index: int
    purpose: str
    visible: bool
    disabled: bool
    multiple: bool
    accept: str
    nearby_text: str
    top: float = 0
    left: float = 0

    def to_mapping(self) -> dict[str, Any]:
        return {
            "file_input_index": self.file_input_index,
            "purpose": self.purpose,
            "visible": self.visible,
            "disabled": self.disabled,
            "multiple": self.multiple,
            "accept": self.accept,
            "nearby_text": self.nearby_text,
            "top": self.top,
            "left": self.left,
        }


def draft_data_from_product(product: ProductDraft) -> DraftSpikeData:
    skus = tuple(_draft_sku_from_product_sku(sku) for sku in product.skus)
    reference_price = max(_reference_price_for_product_sku(sku) for sku in product.skus)
    return DraftSpikeData(
        title=product.title,
        skus=skus,
        reference_price=reference_price,
        product_code=product.product_code,
    )


def main_image_from_product(product: ProductDraft) -> ProductImage:
    for image in product.images:
        if image.role == "main":
            return image
    raise ValueError("product has no main image")


def images_from_product(product: ProductDraft, role: str) -> tuple[ProductImage, ...]:
    return tuple(image for image in product.images if image.role == role)


def fill_minimal_draft_fields(
    page: Any,
    data: DraftSpikeData,
    *,
    sku_images: tuple[SkuImageUpload, ...] = (),
) -> list[str]:
    notes: list[str] = []

    dismiss_known_tips(page)
    click_optional_button(page, "一键复用", notes)
    dismiss_known_tips(page)

    page.get_by_placeholder("商品标题组成").fill(data.title)
    notes.append("filled title")

    sorted_skus = sort_skus_for_page(data.skus)
    option_groups = sku_option_groups(sorted_skus)
    processed_groups: list[str] = []
    for group in option_groups:
        if group.attribute == "颜色分类":
            notes.extend(fill_color_sku_options(page, group.values, sku_images))
        else:
            notes.extend(select_sku_option_values(page, group))
        processed_groups.append(format_sku_option_group(group))
    notes.append(f"processed sku options: {'; '.join(processed_groups)}")
    page.wait_for_timeout(2_000)

    sku_fill_method = fill_sku_table(page, sorted_skus)
    fill_first_placeholder(page, "应大于商品最大单买价", _format_decimal(data.reference_price))
    if data.product_code:
        if fill_product_code(page, data.product_code):
            notes.append("filled product code")
        else:
            notes.append("product code input not found")
    notes.append(f"filled sku stock and prices via {sku_fill_method}")

    return notes


def upload_extra_images(
    page: Any,
    *,
    main_images: tuple[Path, ...] = (),
    detail_images: tuple[Path, ...],
    sku_images: tuple[Path, ...] = (),
) -> tuple[list[str], list[UploadTarget]]:
    notes: list[str] = []
    targets = scan_upload_targets(page)

    if main_images:
        main_target = first_upload_target(targets, "main")
        if main_target is None:
            notes.append("main image upload target not found")
        else:
            page.locator("input[type=file]").nth(main_target.file_input_index).set_input_files(
                [str(path) for path in main_images]
            )
            wait_for_uploads_to_settle(page)
            notes.append(f"uploaded extra main images: {len(main_images)}")

    if detail_images:
        targets = scan_upload_targets(page)
        detail_target = detail_upload_target(targets)
        if detail_target is None:
            raise ValueError("detail image upload target not found or unsafe; stopped to avoid uploading details into SKU")
        else:
            page.locator("input[type=file]").nth(detail_target.file_input_index).set_input_files(
                [str(path) for path in detail_images]
            )
            wait_for_uploads_to_settle(page)
            notes.append(f"uploaded detail images: {len(detail_images)}")

    if sku_images:
        targets = scan_upload_targets(page)
        sku_targets = [target for target in targets if target.purpose == "sku"]
        if not sku_targets:
            notes.append("sku image upload target not found")
        else:
            uploaded_count = 0
            ordered_targets = sorted(sku_targets, key=lambda item: item.file_input_index)
            for target, sku_image in zip(ordered_targets, sku_images, strict=False):
                try:
                    page.locator("input[type=file]").nth(target.file_input_index).set_input_files(
                        str(sku_image),
                        timeout=10_000,
                    )
                except Exception as exc:
                    notes.append(f"sku image upload failed at input {target.file_input_index}: {exc}")
                else:
                    uploaded_count += 1
                    page.wait_for_timeout(700)
            wait_for_uploads_to_settle(page)
            notes.append(f"uploaded sku images: {uploaded_count}/{len(sku_images)}")
            if len(sku_targets) != len(sku_images):
                notes.append(f"sku image target count differs from image count: {len(sku_targets)}/{len(sku_images)}")

    return notes, targets


def scan_upload_targets(page: Any) -> list[UploadTarget]:
    raw_targets = page.evaluate(
        """() => {
            const compact = text => String(text || "").replace(/\\s+/g, " ").trim();
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const textOf = el => compact(el.innerText || el.textContent || "");
            const ancestorTexts = el => {
                const texts = [];
                let current = el;
                for (let depth = 0; current && depth < 10; depth += 1) {
                    const text = textOf(current);
                    if (text && text.length <= 800) texts.push(text);
                    current = current.parentElement;
                }
                return texts;
            };
            const purposeOf = texts => {
                const text = texts.join(" ");
                if (
                    text.includes("价格及库存") ||
                    (text.includes("拼单价") && text.includes("单买价") && text.includes("图片"))
                ) {
                    return "sku";
                }
                if (text.includes("快捷编辑") || text.includes("商品详情") || text.includes("已上传0/50")) {
                    return "detail";
                }
                if (text.includes("商品轮播图") || text.includes("主轮播图")) {
                    return "main";
                }
                if (text.includes("白底图")) {
                    return "white_background";
                }
                return "unknown";
            };

            return Array.from(document.querySelectorAll("input[type=file]")).map((el, fileInputIndex) => {
                const texts = ancestorTexts(el);
                const rect = el.getBoundingClientRect();
                const nearbyText = texts.find(text => (
                    text.includes("商品详情") ||
                    text.includes("快捷编辑") ||
                    text.includes("价格及库存") ||
                    text.includes("批量设置") ||
                    text.includes("商品轮播图") ||
                    text.includes("主轮播图") ||
                    text.includes("白底图")
                )) || texts.find(text => text.length > 8) || texts[0] || "";
                return {
                    file_input_index: fileInputIndex,
                    purpose: purposeOf(texts),
                    visible: visible(el),
                    disabled: !!el.disabled,
                    multiple: !!el.multiple,
                    accept: el.accept || "",
                    nearby_text: nearbyText,
                    top: rect.top,
                    left: rect.left,
                };
            });
        }"""
    )

    targets = [
        UploadTarget(
            file_input_index=int(item.get("file_input_index", 0)),
            purpose=str(item.get("purpose", "unknown")),
            visible=bool(item.get("visible", False)),
            disabled=bool(item.get("disabled", False)),
            multiple=bool(item.get("multiple", False)),
            accept=str(item.get("accept", "")),
            nearby_text=str(item.get("nearby_text", "")),
            top=float(item.get("top", 0) or 0),
            left=float(item.get("left", 0) or 0),
        )
        for item in raw_targets
    ]
    return classify_sku_upload_targets(targets)


def classify_sku_upload_targets(targets: list[UploadTarget]) -> list[UploadTarget]:
    batch_indexes = [
        target.file_input_index
        for target in targets
        if target.purpose == "unknown" and "批量设置" in target.nearby_text
    ]
    if not batch_indexes:
        return targets

    batch_index = min(batch_indexes)
    return [
        replace(target, purpose="sku")
        if (
            target.purpose == "unknown"
            and target.file_input_index > batch_index
            and target.visible
            and not target.disabled
            and "image" in target.accept
        )
        else target
        for target in targets
    ]


def first_upload_target(targets: list[UploadTarget], purpose: str) -> UploadTarget | None:
    for target in targets:
        if target.purpose == purpose and not target.disabled:
            return target
    return None


def detail_upload_target(targets: list[UploadTarget]) -> UploadTarget | None:
    candidates = [
        target
        for target in targets
        if (
            target.purpose == "detail"
            and not target.disabled
            and "image" in target.accept
            and _looks_like_detail_upload_target(target)
        )
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda target: (not target.visible, target.file_input_index))[0]


def _looks_like_detail_upload_target(target: UploadTarget) -> bool:
    text = target.nearby_text
    if "价格及库存" in text or "拼单价" in text or "批量设置" in text:
        return False
    return any(marker in text for marker in ("商品详情", "快捷编辑", "已上传0/50", "详情图", "上传详情图"))


def save_draft(page: Any) -> list[str]:
    notes: list[str] = []
    page.get_by_role("button", name="保存草稿").click(timeout=15_000)
    notes.append("clicked save draft")
    page.wait_for_timeout(6_000)
    return notes


def detect_draft_saved(page: Any) -> bool:
    text = page.locator("body").inner_text(timeout=5_000)
    return any(
        marker in text
        for marker in (
            "保存成功",
            "草稿",
            "商品列表",
            "编辑商品",
        )
    )


def dismiss_known_tips(page: Any) -> None:
    for _ in range(4):
        buttons = page.get_by_role("button", name="知道了")
        if buttons.count() == 0:
            return
        try:
            buttons.first.click(timeout=1_500)
        except Exception:
            return
        page.wait_for_timeout(500)


def click_optional_button(page: Any, name: str, notes: list[str]) -> None:
    button = page.get_by_role("button", name=name)
    if button.count() == 0:
        notes.append(f"optional button not found: {name}")
        return
    try:
        button.first.click(timeout=3_000)
    except Exception as exc:
        notes.append(f"optional button failed: {name}: {exc}")
    else:
        notes.append(f"clicked optional button: {name}")
        page.wait_for_timeout(1_000)


def click_label_by_exact_text(page: Any, text: str) -> bool:
    return bool(page.evaluate(
        """target => {
            const compact = value => (value || "").replace(/\\s+/g, " ").trim();
            const label = Array.from(document.querySelectorAll("label"))
                .find(el => compact(el.innerText || el.textContent) === target);
            if (!label) {
                return false;
            }
            label.click();
            return true;
        }""",
        text,
    ))


def select_sku_option_values(page: Any, group: SkuOptionGroup) -> list[str]:
    notes: list[str] = []
    for value in group.values:
        if click_label_by_exact_text(page, value):
            continue
        notes.append(f"sku option not found: {format_sku_option(group.attribute, value)}")
    return notes


def fill_color_sku_options(
    page: Any,
    values: tuple[str, ...],
    sku_images: tuple[SkuImageUpload, ...],
) -> list[str]:
    notes: list[str] = []
    color_inputs = page.get_by_placeholder("选择或输入主色")
    if color_inputs.count() == 0:
        fallback_group = SkuOptionGroup("颜色分类", values)
        notes.append("color sku input not found; falling back to label selection")
        return notes + select_sku_option_values(page, fallback_group)

    image_by_value = first_sku_image_by_value(sku_images, "颜色分类")
    created_count = 0
    for value in values:
        try:
            select_or_create_color_sku_option(page, value)
        except Exception as exc:
            notes.append(f"color sku option failed: {value}: {exc}")
            continue
        created_count += 1

    uploaded_count = 0
    if image_by_value:
        targets = color_sku_upload_targets(scan_upload_targets(page), expected_count=len(values))
        uploads: list[tuple[UploadTarget, str, SkuImageUpload]] = []
        for index, value in enumerate(values):
            image = image_by_value.get(value)
            if image is None:
                continue
            if index >= len(targets):
                notes.append(f"color sku image upload target not found: {value}")
                continue
            uploads.append((targets[index], value, image))
        for target, value, image in sorted(uploads, key=lambda item: item[0].file_input_index, reverse=True):
            try:
                page.locator("input[type=file]").nth(target.file_input_index).set_input_files(
                    str(image.path),
                    timeout=15_000,
                )
            except Exception as exc:
                notes.append(f"color sku image upload failed: {value}: {exc}")
            else:
                uploaded_count += 1
                page.wait_for_timeout(700)
        wait_for_uploads_to_settle(page)

    notes.append(f"processed color sku options: {created_count}/{len(values)}")
    if image_by_value:
        notes.append(f"uploaded color sku images: {uploaded_count}/{len(image_by_value)}")
    return notes


def color_sku_upload_targets(targets: list[UploadTarget], *, expected_count: int) -> list[UploadTarget]:
    sku_table_indexes = [
        target.file_input_index
        for target in targets
        if target.purpose == "sku" or "批量设置" in target.nearby_text
    ]
    sku_table_index = min(sku_table_indexes) if sku_table_indexes else None
    candidates = [
        target
        for target in targets
        if (
            target.purpose == "unknown"
            and target.visible
            and not target.disabled
            and "image" in target.accept
            and (sku_table_index is None or target.file_input_index < sku_table_index)
        )
    ]
    return sorted(candidates, key=lambda target: (int(target.top // 20), target.left))[:expected_count]


def wait_for_uploads_to_settle(page: Any, *, timeout_ms: int = 60_000) -> bool:
    try:
        page.wait_for_function(
            """() => {
                const compact = value => String(value || "").replace(/\\s+/g, " ").trim();
                const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const bodyText = compact(document.body ? document.body.innerText : "");
                const pendingMarkers = ["上传中", "正在上传", "上传图片中", "图片上传中", "处理中"];
                if (pendingMarkers.some(marker => bodyText.includes(marker))) {
                    return false;
                }
                const busySelectors = [
                    "[aria-busy='true']",
                    "[class*='progress']",
                    "[class*='Progress']",
                    "[class*='uploading']",
                    "[class*='Uploading']",
                    "[class*='spin']",
                    "[class*='Spin']",
                    "[class*='loading']",
                    "[class*='Loading']"
                ];
                return !Array.from(document.querySelectorAll(busySelectors.join(","))).some(el => {
                    const text = compact(el.innerText || el.textContent || el.className || "");
                    return visible(el) && (
                        text.includes("上传") ||
                        text.includes("加载") ||
                        text.includes("处理") ||
                        String(el.getAttribute("aria-busy") || "") === "true"
                    );
                });
            }""",
            timeout=timeout_ms,
        )
    except Exception:
        return False
    page.wait_for_timeout(3_000)
    return True


def select_or_create_color_sku_option(page: Any, value: str) -> None:
    input_index = first_empty_color_input_index(page)
    if input_index is None:
        raise ValueError("empty color sku input not found")

    color_input = page.get_by_placeholder("选择或输入主色").nth(input_index)
    color_input.click(timeout=8_000)
    color_input.fill(value)
    page.wait_for_timeout(300)
    if click_visible_dropdown_option(page, value):
        page.wait_for_timeout(500)
        return

    color_input.press("Enter", timeout=3_000)
    page.wait_for_timeout(300)
    try:
        color_input.press("Tab", timeout=3_000)
    except Exception:
        pass
    page.wait_for_timeout(300)


def first_empty_color_input_index(page: Any) -> int | None:
    index = page.evaluate(
        """() => {
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const inputs = Array.from(document.querySelectorAll('input[placeholder="选择或输入主色"]'))
                .filter(visible);
            const index = inputs.findIndex(el => !String(el.value || "").trim());
            return index >= 0 ? index : null;
        }"""
    )
    return int(index) if index is not None else None


def click_visible_dropdown_option(page: Any, text: str) -> bool:
    return bool(page.evaluate(
        """target => {
            const compact = value => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const selectors = [
                "[role=option]",
                "[role=menuitem]",
                "li",
                ".PP_select_menu_item",
                ".PP_dropdown_menu_item",
                ".ant-select-item-option"
            ];
            const candidates = Array.from(document.querySelectorAll(selectors.join(",")))
                .filter(el => visible(el) && compact(el.innerText || el.textContent) === target);
            if (!candidates.length) {
                return false;
            }
            candidates[0].click();
            return true;
        }""",
        text,
    ))


def field_input_index_by_label(page: Any, label_text: str) -> int | None:
    index = page.evaluate(
        """target => {
            const compact = value => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const labelMatches = el => {
                const text = compact(el.innerText || el.textContent);
                const normalized = text.replace(/[＊*:：]/g, "");
                return text === target || normalized === target;
            };
            const allInputs = Array.from(document.querySelectorAll("input"));
            const eligibleInputs = root => Array.from(root.querySelectorAll("input"))
                .filter(el => (
                    visible(el) &&
                    String(el.type || "").toLowerCase() !== "file" &&
                    String(el.type || "").toLowerCase() !== "hidden" &&
                    !el.disabled
                ));
            const firstInputIndex = root => {
                const inputs = eligibleInputs(root);
                return inputs.length ? allInputs.indexOf(inputs[0]) : null;
            };
            const siblingInputIndex = el => {
                let sibling = el.nextElementSibling;
                for (let steps = 0; sibling && steps < 4; steps += 1) {
                    const index = firstInputIndex(sibling);
                    if (index !== null && index >= 0) return index;
                    sibling = sibling.nextElementSibling;
                }
                return null;
            };
            const labels = Array.from(document.querySelectorAll("label, span, div"))
                .filter(el => visible(el) && labelMatches(el));
            for (const label of labels) {
                let current = label;
                for (let depth = 0; current && depth < 6; depth += 1) {
                    const siblingIndex = siblingInputIndex(current);
                    if (siblingIndex !== null) return siblingIndex;

                    const ownIndex = firstInputIndex(current);
                    if (ownIndex !== null && ownIndex >= 0) return ownIndex;

                    const text = compact(current.innerText || current.textContent);
                    if (text.length > 500 && depth > 1) break;
                    current = current.parentElement;
                }
            }
            return null;
        }""",
        label_text,
    )
    return int(index) if index is not None else None


def first_sku_image_by_value(
    sku_images: tuple[SkuImageUpload, ...],
    attribute: str,
) -> dict[str, SkuImageUpload]:
    images: dict[str, SkuImageUpload] = {}
    for image in sku_images:
        if image.sku_attribute != attribute or not image.sku_value:
            continue
        images.setdefault(image.sku_value, image)
    return images


def fill_product_code(page: Any, product_code: str) -> bool:
    input_index = field_input_index_by_label(page, "商品编码")
    if input_index is None:
        return False
    page.locator("input").nth(int(input_index)).fill(product_code)
    return True


def fill_sku_table(page: Any, skus: tuple[DraftSkuData, ...]) -> str:
    batch_sku = uniform_batch_sku(skus)
    if batch_sku is not None:
        fill_batch_sku_values(page, batch_sku)
        return "batch setting"

    stock_inputs = page.get_by_placeholder("库存")
    group_price_inputs = page.get_by_placeholder("拼单价")
    single_price_inputs = page.get_by_placeholder("单买价")

    if stock_inputs.count() < len(skus):
        fill_batch_sku_values(page, skus[0])
        return "batch setting"

    if group_price_inputs.count() < len(skus):
        raise ValueError(f"expected at least {len(skus)} group price inputs, found {group_price_inputs.count()}")
    if single_price_inputs.count() < len(skus):
        raise ValueError(f"expected at least {len(skus)} single price inputs, found {single_price_inputs.count()}")

    for index, sku in enumerate(skus):
        stock_inputs.nth(index).fill(str(sku.stock))
        group_price_inputs.nth(index).fill(_format_decimal(sku.group_price))
        single_price_inputs.nth(index).fill(_format_decimal(sku.single_price))
    return "row inputs"


def uniform_batch_sku(skus: tuple[DraftSkuData, ...]) -> DraftSkuData | None:
    if not skus:
        return None
    first = skus[0]
    for sku in skus[1:]:
        if (
            sku.stock != first.stock
            or sku.group_price != first.group_price
            or sku.single_price != first.single_price
        ):
            return None
    return first


def fill_batch_sku_values(page: Any, sku: DraftSkuData) -> None:
    fill_first_placeholder(page, "库存", str(sku.stock))
    fill_first_placeholder(page, "拼单价", _format_decimal(sku.group_price))
    fill_first_placeholder(page, "单买价", _format_decimal(sku.single_price))
    page.wait_for_timeout(500)
    page.get_by_role("button", name="批量设置").click(timeout=8_000)
    page.wait_for_timeout(1_500)


def fill_first_placeholder(page: Any, placeholder: str, value: str) -> None:
    page.get_by_placeholder(placeholder).first.fill(value)


def sort_skus_for_page(skus: tuple[DraftSkuData, ...]) -> tuple[DraftSkuData, ...]:
    if any(len(sku.option_values) > 1 for sku in skus):
        return skus
    return tuple(sorted(skus, key=lambda sku: _size_sort_key(sku.size)))


def sku_option_groups(skus: tuple[DraftSkuData, ...]) -> tuple[SkuOptionGroup, ...]:
    groups: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for sku in skus:
        option_pairs = sku.attribute_values
        if not option_pairs:
            option_pairs = tuple(("", value) for value in (sku.option_values or (sku.size,)))
        for attribute, value in option_pairs:
            if not value:
                continue
            if attribute not in groups:
                groups[attribute] = []
                seen[attribute] = set()
            if value in seen[attribute]:
                continue
            seen[attribute].add(value)
            groups[attribute].append(value)

    return tuple(
        SkuOptionGroup(attribute=attribute, values=tuple(values))
        for attribute, values in groups.items()
    )


def format_sku_option_group(group: SkuOptionGroup) -> str:
    values = ", ".join(group.values)
    if group.attribute:
        return f"{group.attribute}: {values}"
    return values


def format_sku_option(attribute: str, value: str) -> str:
    if attribute:
        return f"{attribute}={value}"
    return value


def _format_decimal(value: Decimal) -> str:
    return f"{value:.2f}"


def _draft_sku_from_product_sku(sku: ProductSku) -> DraftSkuData:
    single_price = sku.single_price if sku.single_price is not None else sku.price + Decimal("1.00")
    option_values = tuple(sku.attributes.values()) if sku.attributes else (sku.name,)
    return DraftSkuData(
        size=sku.name,
        stock=sku.stock,
        group_price=sku.price,
        single_price=single_price,
        option_values=option_values,
        attribute_values=tuple(sku.attributes.items()),
    )


def _reference_price_for_product_sku(sku: ProductSku) -> Decimal:
    single_price = sku.single_price if sku.single_price is not None else sku.price + Decimal("1.00")
    return sku.reference_price if sku.reference_price is not None else single_price + Decimal("1.00")


def _size_sort_key(size: str) -> tuple[int, Decimal | str]:
    try:
        return (0, Decimal(size))
    except Exception:
        return (1, size)


def unique_sku_option_values(skus: tuple[DraftSkuData, ...]) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for group in sku_option_groups(skus):
        for value in group.values:
            if value and value not in seen:
                seen.add(value)
                values.append(value)
    return tuple(values)

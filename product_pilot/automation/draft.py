"""Minimal draft filling helpers for the product publish spike."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class DraftSpikeData:
    title: str = "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋"
    skus: tuple[DraftSkuData, ...] = (DraftSkuData(),)
    reference_price: Decimal = Decimal("99.00")


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


def draft_data_from_product(product: ProductDraft) -> DraftSpikeData:
    skus = tuple(_draft_sku_from_product_sku(sku) for sku in product.skus)
    reference_price = max(_reference_price_for_product_sku(sku) for sku in product.skus)
    return DraftSpikeData(
        title=product.title,
        skus=skus,
        reference_price=reference_price,
    )


def main_image_from_product(product: ProductDraft) -> ProductImage:
    for image in product.images:
        if image.role == "main":
            return image
    raise ValueError("product has no main image")


def fill_minimal_draft_fields(page: Any, data: DraftSpikeData) -> list[str]:
    notes: list[str] = []

    dismiss_known_tips(page)
    click_optional_button(page, "一键复用", notes)
    dismiss_known_tips(page)

    page.get_by_placeholder("商品标题组成").fill(data.title)
    notes.append("filled title")

    sorted_skus = sort_skus_for_page(data.skus)
    for sku in sorted_skus:
        click_label_by_exact_text(page, sku.size)
    notes.append(f"selected sizes: {', '.join(sku.size for sku in sorted_skus)}")
    page.wait_for_timeout(2_000)

    fill_sku_table(page, sorted_skus)
    fill_first_placeholder(page, "应大于商品最大单买价", _format_decimal(data.reference_price))
    notes.append("filled sku stock and prices")

    return notes


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


def click_label_by_exact_text(page: Any, text: str) -> None:
    page.evaluate(
        """target => {
            const compact = value => (value || "").replace(/\\s+/g, " ").trim();
            const label = Array.from(document.querySelectorAll("label"))
                .find(el => compact(el.innerText || el.textContent) === target);
            if (!label) {
                throw new Error(`label not found: ${target}`);
            }
            label.click();
        }""",
        text,
    )


def fill_sku_table(page: Any, skus: tuple[DraftSkuData, ...]) -> None:
    stock_inputs = page.get_by_placeholder("库存")
    group_price_inputs = page.get_by_placeholder("拼单价")
    single_price_inputs = page.get_by_placeholder("单买价")

    if stock_inputs.count() < len(skus):
        fill_batch_sku_values(page, skus[0])
        return

    if group_price_inputs.count() < len(skus):
        raise ValueError(f"expected at least {len(skus)} group price inputs, found {group_price_inputs.count()}")
    if single_price_inputs.count() < len(skus):
        raise ValueError(f"expected at least {len(skus)} single price inputs, found {single_price_inputs.count()}")

    for index, sku in enumerate(skus):
        stock_inputs.nth(index).fill(str(sku.stock))
        group_price_inputs.nth(index).fill(_format_decimal(sku.group_price))
        single_price_inputs.nth(index).fill(_format_decimal(sku.single_price))


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
    return tuple(sorted(skus, key=lambda sku: _size_sort_key(sku.size)))


def _format_decimal(value: Decimal) -> str:
    return f"{value:.2f}"


def _draft_sku_from_product_sku(sku: ProductSku) -> DraftSkuData:
    single_price = sku.single_price if sku.single_price is not None else sku.price
    return DraftSkuData(
        size=sku.name,
        stock=sku.stock,
        group_price=sku.price,
        single_price=single_price,
    )


def _reference_price_for_product_sku(sku: ProductSku) -> Decimal:
    single_price = sku.single_price if sku.single_price is not None else sku.price
    return sku.reference_price if sku.reference_price is not None else single_price + Decimal("1.00")


def _size_sort_key(size: str) -> tuple[int, Decimal | str]:
    try:
        return (0, Decimal(size))
    except Exception:
        return (1, size)

"""Minimal draft filling helpers for the product publish spike."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DraftSpikeData:
    title: str = "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋"
    size: str = "42"
    stock: int = 10
    group_price: Decimal = Decimal("29.90")
    single_price: Decimal = Decimal("39.90")
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


def fill_minimal_draft_fields(page: Any, data: DraftSpikeData) -> list[str]:
    notes: list[str] = []

    dismiss_known_tips(page)
    click_optional_button(page, "一键复用", notes)
    dismiss_known_tips(page)

    page.get_by_placeholder("商品标题组成").fill(data.title)
    notes.append("filled title")

    click_label_by_exact_text(page, data.size)
    notes.append(f"selected size: {data.size}")
    page.wait_for_timeout(2_000)

    fill_first_placeholder(page, "库存", str(data.stock))
    fill_first_placeholder(page, "拼单价", _format_decimal(data.group_price))
    fill_first_placeholder(page, "单买价", _format_decimal(data.single_price))
    fill_first_placeholder(page, "应大于商品最大单买价", _format_decimal(data.reference_price))
    notes.append("filled stock and prices")

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


def fill_first_placeholder(page: Any, placeholder: str, value: str) -> None:
    page.get_by_placeholder(placeholder).first.fill(value)


def _format_decimal(value: Decimal) -> str:
    return f"{value:.2f}"


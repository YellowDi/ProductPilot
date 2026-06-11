"""Category selection helpers for the publish flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_CATEGORY_PATH = ("流行男鞋", "低帮鞋", "板鞋")


@dataclass(frozen=True)
class CategorySelectionResult:
    path: tuple[str, ...]
    selected_from_recommendation: bool
    confirmed: bool
    notes: list[str]

    @property
    def display_path(self) -> str:
        return format_category_path(self.path)


def parse_category_path(value: str) -> tuple[str, ...]:
    parts = [part.strip() for part in value.replace("/", ">").split(">")]
    return tuple(part for part in parts if part)


def format_category_path(path: tuple[str, ...]) -> str:
    return " > ".join(path)


def select_category(page: Any, path: tuple[str, ...]) -> CategorySelectionResult:
    notes: list[str] = []
    target = format_category_path(path)

    dismissed_recommendations = dismiss_recommended_category_modals(page, notes)
    if dismissed_recommendations:
        notes.append(
            f"will select configured category after closing {dismissed_recommendations} recommendation modal(s)"
        )
    elif select_recommended_category(page, target):
        notes.append(f"selected recommended category: {target}")
        return CategorySelectionResult(
            path=path,
            selected_from_recommendation=True,
            confirmed=True,
            notes=notes,
        )

    if not dismissed_recommendations:
        notes.append("recommendation modal not found or target category not present")
    if select_recent_category(page, target):
        notes.append(f"selected recent category: {target}")
        return CategorySelectionResult(
            path=path,
            selected_from_recommendation=False,
            confirmed=True,
            notes=notes,
        )

    for part in path:
        dismiss_recommended_category_modals(page, notes, wait_timeout_ms=500)
        page.locator("li.content-cat").filter(has_text=part).first.click(timeout=10_000)
        page.wait_for_timeout(800)

    page.wait_for_function(
        """target => {
            const text = document.body ? document.body.innerText : "";
            return text.includes(target);
        }""",
        arg=target,
    )
    notes.append(f"selected category columns: {target}")
    return CategorySelectionResult(
        path=path,
        selected_from_recommendation=False,
        confirmed=True,
        notes=notes,
    )


def select_recommended_category(page: Any, target: str) -> bool:
    body_text = page.locator("body").inner_text(timeout=3_000)
    if "根据您上传的图片，为您推荐分类，请选择" not in body_text:
        return False
    if target not in body_text:
        return False

    clicked = page.evaluate(
        """target => {
            const compact = value => (value || "").replace(/\\s+/g, " ").trim();
            const optionText = Array.from(document.querySelectorAll(".catPredictAlert_multiLabel__UwvmJ"))
                .find(el => compact(el.innerText || el.textContent) === target);
            if (!optionText) {
                return false;
            }
            const label = optionText.closest("label");
            (label || optionText).click();
            return true;
        }""",
        target,
    )
    if not clicked:
        return False
    page.get_by_role("button", name="确认").first.click(timeout=10_000, force=True)
    page.wait_for_timeout(2_000)
    return True


def dismiss_recommended_category_modals(
    page: Any,
    notes: list[str] | None = None,
    *,
    max_attempts: int = 5,
    wait_timeout_ms: int = 2_000,
    poll_interval_ms: int = 250,
) -> int:
    dismissed = 0
    waited = 0
    for _ in range(max_attempts):
        if not dismiss_recommended_category_modal(page, notes):
            if dismissed or waited >= wait_timeout_ms:
                return dismissed
            wait_ms = min(poll_interval_ms, wait_timeout_ms - waited)
            page.wait_for_timeout(wait_ms)
            waited += wait_ms
            continue
        waited = wait_timeout_ms
        dismissed += 1
    if notes is not None:
        notes.append(f"stopped after closing {dismissed} recommended category modal(s)")
    return dismissed


def dismiss_recommended_category_modal(page: Any, notes: list[str] | None = None) -> bool:
    action = page.evaluate(
        """() => {
            const compact = value => String(value || "").replace(/\\s+/g, " ").trim();
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const markers = [
                "根据您上传的图片，为您推荐分类，请选择",
                "建议商品分类",
                "建议分类",
                "推荐分类",
                "推荐类目"
            ];
            const hasMarker = el => {
                const text = compact(el.innerText || el.textContent);
                return markers.some(marker => text.includes(marker));
            };
            const closeNames = ["关闭", "取消", "暂不选择", "不选择", "跳过", "稍后再说"];
            const clickTextButton = root => {
                const controls = Array.from(root.querySelectorAll('button, [role="button"], a'))
                    .filter(visible);
                for (const name of closeNames) {
                    const control = controls.find(el => compact(el.innerText || el.textContent) === name);
                    if (control) {
                        control.click();
                        return name;
                    }
                }
                return "";
            };
            const clickCloseIcon = root => {
                const controls = Array.from(root.querySelectorAll('button, [role="button"], a, span, i, svg'))
                    .filter(visible);
                const control = controls.find(el => {
                    const aria = compact(el.getAttribute("aria-label"));
                    const title = compact(el.getAttribute("title"));
                    const className = String(el.className || "").toLowerCase();
                    return aria.includes("关闭")
                        || title.includes("关闭")
                        || aria.toLowerCase().includes("close")
                        || title.toLowerCase().includes("close")
                        || className.includes("close");
                });
                if (!control) {
                    return "";
                }
                (control.closest('button, [role="button"], a') || control).click();
                return "close-icon";
            };
            const modalSelectors = [
                '[role="dialog"]',
                '[data-testid="beast-core-modal"]',
                '[class*="catPredictAlert"]',
                '[class*="MDL_outerWrapper"]',
                '[class*="modal"]',
                '[class*="Modal"]'
            ];
            const modalRoots = Array.from(document.querySelectorAll(modalSelectors.join(",")))
                .filter(el => visible(el) && hasMarker(el));
            const textRoots = Array.from(document.querySelectorAll("div, section, aside"))
                .filter(el => visible(el) && hasMarker(el))
                .sort((a, b) => compact(a.innerText || a.textContent).length - compact(b.innerText || b.textContent).length);
            const roots = modalRoots.length ? modalRoots : textRoots;
            for (const root of roots) {
                let current = root;
                for (let depth = 0; current && current !== document.body && depth < 6; depth += 1) {
                    const byText = clickTextButton(current);
                    if (byText) {
                        return byText;
                    }
                    const byIcon = clickCloseIcon(current);
                    if (byIcon) {
                        return byIcon;
                    }
                    current = current.parentElement;
                }
            }
            return "";
        }"""
    )
    if not action:
        return False
    if notes is not None:
        notes.append(f"dismissed recommended category modal: {action}")
    page.wait_for_timeout(500)
    return True


def select_recent_category(page: Any, target: str) -> bool:
    clicked = page.evaluate(
        """target => {
            const compact = value => String(value || "").replace(/\\s+/g, " ").trim();
            const normalize = value => compact(value).replace(/\\s*>\\s*/g, ">");
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const targetText = normalize(target);
            const candidates = Array.from(document.querySelectorAll("a, button, label, span, div, li"))
                .filter(el => {
                    if (!visible(el)) return false;
                    const text = normalize(el.innerText || el.textContent);
                    return text.includes(targetText) && text.length <= targetText.length + 20;
                });
            if (!candidates.length) {
                return false;
            }
            const exact = candidates.find(el => normalize(el.innerText || el.textContent) === targetText);
            const candidate = exact || candidates[0];
            const clickable = candidate.closest("a, button, label, [role='button'], li") || candidate;
            clickable.click();
            return true;
        }""",
        target,
    )
    if not clicked:
        return False
    page.wait_for_timeout(1_000)
    return True


def click_next_product_info(page: Any, notes: list[str], *, timeout: int = 10_000) -> None:
    dismiss_recommended_category_modals(page, notes, wait_timeout_ms=500)
    dismiss_blocking_modals(page, notes)
    try:
        page.get_by_text("下一步, 完善商品信息", exact=True).click(timeout=timeout)
    except Exception as exc:
        if "intercepts pointer events" not in str(exc):
            raise
        dismissed_recommendations = dismiss_recommended_category_modals(page, notes, wait_timeout_ms=1_000)
        dismissed_blocking = dismiss_blocking_modals(page, notes)
        if not dismissed_recommendations and not dismissed_blocking:
            raise
        page.get_by_text("下一步, 完善商品信息", exact=True).click(timeout=timeout)
    page.get_by_placeholder("商品标题组成").wait_for(timeout=timeout)


def dismiss_blocking_modals(page: Any, notes: list[str]) -> bool:
    dismissed = False
    for _ in range(3):
        action = page.evaluate(
            """() => {
                const compact = value => String(value || "").replace(/\\s+/g, " ").trim();
                const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const modals = Array.from(document.querySelectorAll(
                    '[data-testid="beast-core-modal"], [class*="MDL_outerWrapper"]'
                )).filter(visible);
                const buttonNames = ["确认", "确定", "知道了", "我知道了", "关闭"];
                for (const modal of modals) {
                    const buttons = Array.from(modal.querySelectorAll('button, [role="button"]')).filter(visible);
                    for (const name of buttonNames) {
                        const button = buttons.find(el => compact(el.innerText || el.textContent) === name);
                        if (button) {
                            button.click();
                            return name;
                        }
                    }
                }
                return "";
            }"""
        )
        if not action:
            return dismissed
        dismissed = True
        notes.append(f"dismissed blocking modal: {action}")
        page.wait_for_timeout(1_000)
    return dismissed

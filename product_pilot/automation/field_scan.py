"""Generic field scanner for the product publish flow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FieldCandidate:
    index: int
    tag: str
    input_type: str
    placeholder: str
    value: str
    visible: bool
    disabled: bool
    nearby_text: str


@dataclass(frozen=True)
class ActionCandidate:
    index: int
    text: str
    disabled: bool


@dataclass(frozen=True)
class FieldScanResult:
    url: str
    title: str
    required_labels: list[str]
    fields: list[FieldCandidate]
    actions: list[ActionCandidate]
    screenshot_path: Path
    notes: list[str]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "required_labels": self.required_labels,
            "fields": [field.__dict__ for field in self.fields],
            "actions": [action.__dict__ for action in self.actions],
            "screenshot_path": str(self.screenshot_path),
            "notes": self.notes,
        }


def scan_publish_fields(page: Any, screenshot_path: Path, notes: list[str] | None = None) -> FieldScanResult:
    raw = page.evaluate(
        """() => {
            const textOf = el => (el.innerText || el.textContent || "").trim();
            const compact = text => text.replace(/\\s+/g, " ").trim();
            const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
            const nearby = el => {
                const item = el.closest("[class*=form], [class*=Form], [class*=item], [class*=Item], label, div");
                return compact(item ? textOf(item).slice(0, 240) : "");
            };
            const controls = Array.from(document.querySelectorAll("input, textarea, select"))
                .map((el, index) => ({
                    index,
                    tag: el.tagName.toLowerCase(),
                    input_type: el.type || "",
                    placeholder: el.placeholder || "",
                    value: el.type === "file" ? "<file>" : (el.value || ""),
                    visible: visible(el),
                    disabled: !!el.disabled,
                    nearby_text: nearby(el),
                }));
            const actions = Array.from(document.querySelectorAll("button"))
                .map((el, index) => ({
                    index,
                    text: compact(textOf(el)),
                    disabled: !!el.disabled,
                }))
                .filter(action => action.text)
                .slice(0, 120);
            const textBlocks = Array.from(document.querySelectorAll("label, span, div, p"))
                .map(el => compact(textOf(el)))
                .filter(text => text.includes("*") || text.includes("必填"))
                .slice(0, 300);
            return {
                url: location.href,
                title: document.title,
                controls,
                actions,
                textBlocks,
            };
        }"""
    )

    required_labels = extract_required_labels(raw.get("textBlocks", []))
    fields = [
        FieldCandidate(
            index=int(item.get("index", 0)),
            tag=str(item.get("tag", "")),
            input_type=str(item.get("input_type", "")),
            placeholder=str(item.get("placeholder", "")),
            value=str(item.get("value", "")),
            visible=bool(item.get("visible", False)),
            disabled=bool(item.get("disabled", False)),
            nearby_text=str(item.get("nearby_text", "")),
        )
        for item in raw.get("controls", [])
    ]
    actions = [
        ActionCandidate(
            index=int(item.get("index", 0)),
            text=str(item.get("text", "")),
            disabled=bool(item.get("disabled", False)),
        )
        for item in raw.get("actions", [])
    ]

    return FieldScanResult(
        url=str(raw.get("url", "")),
        title=str(raw.get("title", "")),
        required_labels=required_labels,
        fields=fields,
        actions=actions,
        screenshot_path=screenshot_path,
        notes=notes or [],
    )


def extract_required_labels(text_blocks: list[str]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    for block in text_blocks:
        for part in block.replace("：", ":").split("*"):
            label = part.strip().split(":")[0].strip()
            if not label:
                continue
            if len(label) > 40:
                label = label[:40].strip()
            if label and label not in seen and not label.startswith("发布须知"):
                seen.add(label)
                labels.append(label)

    return labels

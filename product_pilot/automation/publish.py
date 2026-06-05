"""Publish page detection for the product listing spike."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PublishPageState(StrEnum):
    READY = "ready"
    LOGIN_REQUIRED = "login_required"
    RISK_CHECK_REQUIRED = "risk_check_required"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PublishPageSnapshot:
    url: str
    title: str
    body_text: str
    has_password_input: bool


@dataclass(frozen=True)
class PublishPageCheckResult:
    state: PublishPageState
    reason: str
    snapshot: PublishPageSnapshot


PUBLISH_TITLE_MARKERS = (
    "发布新商品",
)

PUBLISH_UPLOAD_MARKERS = (
    "上传商品轮播图",
    "上传主轮播图",
    "上传图片",
)

PUBLISH_CATEGORY_MARKERS = (
    "选择商品分类",
    "商品分类",
)

RISK_CHECK_MARKERS = (
    "请向右滑块完成拼图",
    "滑块完成拼图",
    "完成拼图",
)

LOGIN_MARKERS = (
    "账号登录",
    "密码登录",
    "扫码登录",
    "请登录",
)

PUBLISH_PAGE_LOAD_MARKERS = (
    *PUBLISH_TITLE_MARKERS,
    *PUBLISH_UPLOAD_MARKERS,
    *PUBLISH_CATEGORY_MARKERS,
    *RISK_CHECK_MARKERS,
    *LOGIN_MARKERS,
)


def read_publish_page_snapshot(page: Any) -> PublishPageSnapshot:
    return PublishPageSnapshot(
        url=str(getattr(page, "url", "")),
        title=_safe_page_title(page),
        body_text=_safe_body_text(page),
        has_password_input=_safe_has_password_input(page),
    )


def classify_publish_page_snapshot(snapshot: PublishPageSnapshot) -> PublishPageCheckResult:
    body_text = snapshot.body_text

    if snapshot.has_password_input or any(marker in body_text for marker in LOGIN_MARKERS):
        return PublishPageCheckResult(
            state=PublishPageState.LOGIN_REQUIRED,
            reason="login form markers are present",
            snapshot=snapshot,
        )

    if any(marker in body_text for marker in RISK_CHECK_MARKERS):
        return PublishPageCheckResult(
            state=PublishPageState.RISK_CHECK_REQUIRED,
            reason="manual slider or risk check is present",
            snapshot=snapshot,
        )

    if (
        any(marker in body_text for marker in PUBLISH_TITLE_MARKERS)
        and any(marker in body_text for marker in PUBLISH_UPLOAD_MARKERS)
        and any(marker in body_text for marker in PUBLISH_CATEGORY_MARKERS)
    ):
        return PublishPageCheckResult(
            state=PublishPageState.READY,
            reason="publish category page markers are present",
            snapshot=snapshot,
        )

    return PublishPageCheckResult(
        state=PublishPageState.UNKNOWN,
        reason="no stable publish page markers found",
        snapshot=snapshot,
    )


def _safe_page_title(page: Any) -> str:
    try:
        return str(page.title())
    except Exception:
        return ""


def _safe_body_text(page: Any) -> str:
    try:
        return str(page.locator("body").inner_text(timeout=2_000))
    except Exception:
        return ""


def _safe_has_password_input(page: Any) -> bool:
    try:
        return page.locator("input[type='password']").count() > 0
    except Exception:
        return False

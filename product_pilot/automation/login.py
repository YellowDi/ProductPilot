"""Login state detection for the merchant backend."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class LoginState(StrEnum):
    LOGGED_IN = "logged_in"
    LOGIN_REQUIRED = "login_required"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LoginSnapshot:
    url: str
    title: str
    body_text: str
    has_password_input: bool


@dataclass(frozen=True)
class LoginCheckResult:
    state: LoginState
    reason: str
    snapshot: LoginSnapshot


LOGIN_URL_MARKERS = (
    "login",
    "passport",
)

LOGIN_TEXT_MARKERS = (
    "账号登录",
    "密码登录",
    "扫码登录",
    "手机登录",
    "验证码",
    "请登录",
)

AUTH_TEXT_MARKERS = (
    "商品管理",
    "发布商品",
    "店铺",
    "订单",
    "营销",
    "售后",
)


def read_login_snapshot(page: Any) -> LoginSnapshot:
    return LoginSnapshot(
        url=str(getattr(page, "url", "")),
        title=_safe_page_title(page),
        body_text=_safe_body_text(page),
        has_password_input=_safe_has_password_input(page),
    )


def classify_login_snapshot(snapshot: LoginSnapshot) -> LoginCheckResult:
    normalized_url = snapshot.url.lower()
    body_text = snapshot.body_text

    if snapshot.has_password_input:
        return LoginCheckResult(
            state=LoginState.LOGIN_REQUIRED,
            reason="password input is visible or attached",
            snapshot=snapshot,
        )

    if any(marker in normalized_url for marker in LOGIN_URL_MARKERS):
        return LoginCheckResult(
            state=LoginState.LOGIN_REQUIRED,
            reason="url looks like a login page",
            snapshot=snapshot,
        )

    if any(marker in body_text for marker in AUTH_TEXT_MARKERS):
        return LoginCheckResult(
            state=LoginState.LOGGED_IN,
            reason="merchant backend navigation text is present",
            snapshot=snapshot,
        )

    if any(marker in body_text for marker in LOGIN_TEXT_MARKERS):
        return LoginCheckResult(
            state=LoginState.LOGIN_REQUIRED,
            reason="login text is present",
            snapshot=snapshot,
        )

    return LoginCheckResult(
        state=LoginState.UNKNOWN,
        reason="no stable login or merchant markers found",
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


from __future__ import annotations

import unittest

from product_pilot.automation.login import LoginSnapshot, LoginState, classify_login_snapshot


class LoginClassifierTests(unittest.TestCase):
    def test_password_input_requires_login(self) -> None:
        result = classify_login_snapshot(
            LoginSnapshot(
                url="https://mms.pinduoduo.com/",
                title="",
                body_text="",
                has_password_input=True,
            )
        )

        self.assertEqual(result.state, LoginState.LOGIN_REQUIRED)

    def test_login_url_requires_login(self) -> None:
        result = classify_login_snapshot(
            LoginSnapshot(
                url="https://mms.pinduoduo.com/login",
                title="",
                body_text="",
                has_password_input=False,
            )
        )

        self.assertEqual(result.state, LoginState.LOGIN_REQUIRED)

    def test_backend_navigation_marks_logged_in(self) -> None:
        result = classify_login_snapshot(
            LoginSnapshot(
                url="https://mms.pinduoduo.com/home",
                title="",
                body_text="商品管理 发布商品 订单 店铺",
                has_password_input=False,
            )
        )

        self.assertEqual(result.state, LoginState.LOGGED_IN)

    def test_unknown_when_no_markers_exist(self) -> None:
        result = classify_login_snapshot(
            LoginSnapshot(
                url="https://mms.pinduoduo.com/",
                title="",
                body_text="loading",
                has_password_input=False,
            )
        )

        self.assertEqual(result.state, LoginState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()


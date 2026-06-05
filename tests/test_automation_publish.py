from __future__ import annotations

import unittest

from product_pilot.automation.publish import (
    PublishPageSnapshot,
    PublishPageState,
    classify_publish_page_snapshot,
)


class PublishPageClassifierTests(unittest.TestCase):
    def test_ready_when_publish_markers_exist(self) -> None:
        result = classify_publish_page_snapshot(
            PublishPageSnapshot(
                url="https://mms.pinduoduo.com/goods/category",
                title="发布新商品",
                body_text="发布新商品 第1步 上传商品轮播图 第2步 选择商品分类",
                has_password_input=False,
            )
        )

        self.assertEqual(result.state, PublishPageState.READY)

    def test_ready_with_alternate_upload_marker(self) -> None:
        result = classify_publish_page_snapshot(
            PublishPageSnapshot(
                url="https://mms.pinduoduo.com/goods/category",
                title="发布新商品",
                body_text="发布新商品 第1步 上传主轮播图 第2步 选择商品分类",
                has_password_input=False,
            )
        )

        self.assertEqual(result.state, PublishPageState.READY)

    def test_risk_check_takes_priority_over_ready_markers(self) -> None:
        result = classify_publish_page_snapshot(
            PublishPageSnapshot(
                url="https://mms.pinduoduo.com/goods/category",
                title="发布新商品",
                body_text="发布新商品 上传商品轮播图 选择商品分类 请向右滑块完成拼图",
                has_password_input=False,
            )
        )

        self.assertEqual(result.state, PublishPageState.RISK_CHECK_REQUIRED)

    def test_login_required_when_password_input_exists(self) -> None:
        result = classify_publish_page_snapshot(
            PublishPageSnapshot(
                url="https://mms.pinduoduo.com/goods/category",
                title="",
                body_text="",
                has_password_input=True,
            )
        )

        self.assertEqual(result.state, PublishPageState.LOGIN_REQUIRED)

    def test_unknown_when_no_markers_exist(self) -> None:
        result = classify_publish_page_snapshot(
            PublishPageSnapshot(
                url="https://mms.pinduoduo.com/goods/category",
                title="",
                body_text="loading",
                has_password_input=False,
            )
        )

        self.assertEqual(result.state, PublishPageState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()

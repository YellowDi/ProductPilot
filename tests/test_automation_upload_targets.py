from __future__ import annotations

import unittest

from product_pilot.automation.draft import UploadTarget, detail_upload_target


class UploadTargetTests(unittest.TestCase):
    def test_detail_upload_target_rejects_sku_context(self) -> None:
        targets = [
            UploadTarget(
                file_input_index=8,
                purpose="detail",
                visible=True,
                disabled=False,
                multiple=True,
                accept="image/jpeg,image/png",
                nearby_text="价格及库存 拼单价 单买价 图片 批量设置",
            )
        ]

        self.assertIsNone(detail_upload_target(targets))

    def test_detail_upload_target_accepts_detail_context(self) -> None:
        targets = [
            UploadTarget(
                file_input_index=4,
                purpose="detail",
                visible=True,
                disabled=False,
                multiple=True,
                accept="image/jpeg,image/png",
                nearby_text="商品详情 快捷编辑 已上传0/50 图片空间上传 本地上传",
            )
        ]

        self.assertEqual(detail_upload_target(targets), targets[0])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from decimal import Decimal

from product_pilot.automation.draft import (
    DraftSkuData,
    DraftSpikeData,
    UploadTarget,
    _format_decimal,
    classify_sku_upload_targets,
    color_sku_upload_targets,
    click_first_optional_button,
    draft_data_from_product,
    images_from_product,
    main_image_from_product,
    sku_option_groups,
    sort_skus_for_page,
    uniform_batch_sku,
    unique_sku_option_values,
)
from product_pilot.domain.product import ProductDraft


class DraftSpikeDataTests(unittest.TestCase):
    def test_default_data_is_valid_for_spike(self) -> None:
        data = DraftSpikeData()

        self.assertGreater(data.skus[0].stock, 0)
        self.assertGreater(data.skus[0].single_price, data.skus[0].group_price)
        self.assertGreater(data.reference_price, data.skus[0].single_price)

    def test_formats_decimal(self) -> None:
        self.assertEqual(_format_decimal(Decimal("29.9")), "29.90")

    def test_maps_product_to_draft_spike_data(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋",
                "category": "流行男鞋 > 低帮鞋 > 板鞋",
                "images": [
                    {"path": "../SKU06.jpg", "role": "main"},
                    {"path": "../SKU06.jpg", "role": "detail"},
                    {"path": "../SKU06.jpg", "role": "sku"},
                ],
                "skus": [
                    {
                        "name": "41",
                        "price": "29.90",
                        "single_price": "39.90",
                        "reference_price": "99.00",
                        "stock": 8,
                    },
                    {
                        "name": "42",
                        "price": "29.90",
                        "single_price": "39.90",
                        "reference_price": "99.00",
                        "stock": 10,
                    }
                ],
            }
        )

        data = draft_data_from_product(product)

        self.assertEqual(data.title, "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋")
        self.assertEqual([sku.size for sku in data.skus], ["41", "42"])
        self.assertEqual(data.skus[0].group_price, Decimal("29.90"))
        self.assertEqual(data.skus[0].single_price, Decimal("39.90"))
        self.assertEqual(data.reference_price, Decimal("99.00"))
        self.assertEqual(main_image_from_product(product).path.as_posix(), "../SKU06.jpg")
        self.assertEqual(len(images_from_product(product, "detail")), 1)
        self.assertEqual(len(images_from_product(product, "sku")), 1)

    def test_sorts_numeric_skus_for_page(self) -> None:
        skus = (
            DraftSkuData(size="43", stock=1, group_price=Decimal("1"), single_price=Decimal("2")),
            DraftSkuData(size="41", stock=1, group_price=Decimal("1"), single_price=Decimal("2")),
            DraftSkuData(size="42.5", stock=1, group_price=Decimal("1"), single_price=Decimal("2")),
        )

        self.assertEqual([sku.size for sku in sort_skus_for_page(skus)], ["41", "42.5", "43"])

    def test_keeps_multi_attribute_skus_in_product_order(self) -> None:
        skus = (
            DraftSkuData(
                size="黑色 38",
                stock=1,
                group_price=Decimal("1"),
                single_price=Decimal("2"),
                option_values=("黑色", "38"),
            ),
            DraftSkuData(
                size="棕色 38",
                stock=1,
                group_price=Decimal("1"),
                single_price=Decimal("2"),
                option_values=("棕色", "38"),
            ),
        )

        self.assertEqual([sku.size for sku in sort_skus_for_page(skus)], ["黑色 38", "棕色 38"])
        self.assertEqual(unique_sku_option_values(skus), ("黑色", "38", "棕色"))

    def test_maps_product_sku_attributes_to_draft_options(self) -> None:
        product = ProductDraft.from_mapping(
            {
                "title": "Multi SKU Product",
                "category": "default-category",
                "product_code": "demo001",
                "images": [{"path": "images/main.jpg", "role": "main"}],
                "skus": [
                    {
                        "name": "黑色 38",
                        "attributes": {"颜色分类": "黑色", "鞋码": "38"},
                        "price": "146.64",
                        "stock": 1000,
                    }
                ],
            }
        )

        data = draft_data_from_product(product)

        self.assertEqual(data.skus[0].size, "黑色 38")
        self.assertEqual(data.product_code, "demo001")
        self.assertEqual(data.skus[0].option_values, ("黑色", "38"))
        self.assertEqual(data.skus[0].attribute_values, (("颜色分类", "黑色"), ("鞋码", "38")))

    def test_groups_sku_options_by_attribute(self) -> None:
        skus = (
            DraftSkuData(
                size="黑色 38",
                stock=1,
                group_price=Decimal("1"),
                single_price=Decimal("2"),
                option_values=("黑色", "38"),
                attribute_values=(("颜色分类", "黑色"), ("鞋码", "38")),
            ),
            DraftSkuData(
                size="黑色 39",
                stock=1,
                group_price=Decimal("1"),
                single_price=Decimal("2"),
                option_values=("黑色", "39"),
                attribute_values=(("颜色分类", "黑色"), ("鞋码", "39")),
            ),
            DraftSkuData(
                size="棕色 38",
                stock=1,
                group_price=Decimal("1"),
                single_price=Decimal("2"),
                option_values=("棕色", "38"),
                attribute_values=(("颜色分类", "棕色"), ("鞋码", "38")),
            ),
        )

        groups = sku_option_groups(skus)

        self.assertEqual([(group.attribute, group.values) for group in groups], [
            ("颜色分类", ("黑色", "棕色")),
            ("鞋码", ("38", "39")),
        ])

    def test_detects_uniform_skus_for_batch_setting(self) -> None:
        skus = (
            DraftSkuData(size="黑色 38", stock=1000, group_price=Decimal("146.64"), single_price=Decimal("146.64")),
            DraftSkuData(size="黑色 39", stock=1000, group_price=Decimal("146.64"), single_price=Decimal("146.64")),
        )

        self.assertIs(uniform_batch_sku(skus), skus[0])

    def test_rejects_mixed_skus_for_batch_setting(self) -> None:
        skus = (
            DraftSkuData(size="黑色 38", stock=1000, group_price=Decimal("146.64"), single_price=Decimal("146.64")),
            DraftSkuData(size="黑色 39", stock=998, group_price=Decimal("146.64"), single_price=Decimal("146.64")),
        )

        self.assertIsNone(uniform_batch_sku(skus))

    def test_classifies_visible_image_inputs_after_batch_upload_as_sku_targets(self) -> None:
        targets = [
            UploadTarget(4, "detail", True, False, True, "image/jpeg,image/png", "图片空间上传本地上传"),
            UploadTarget(7, "unknown", True, False, True, "image/jpeg,image/png", "元 元 本地上传 批量设置"),
            UploadTarget(8, "unknown", True, False, True, "image/jpeg,image/png", "本地上传"),
            UploadTarget(9, "unknown", True, False, True, "image/jpeg,image/png", "本地上传"),
        ]

        classified = classify_sku_upload_targets(targets)

        self.assertEqual([target.purpose for target in classified], ["detail", "unknown", "sku", "sku"])

    def test_selects_color_upload_targets_before_sku_table(self) -> None:
        targets = [
            UploadTarget(4, "detail", True, False, True, "image/jpeg,image/png", "图片空间上传本地上传"),
            UploadTarget(5, "unknown", True, False, True, "image/jpeg,image/png", "本地上传", top=100, left=300),
            UploadTarget(6, "unknown", True, False, True, "image/jpeg,image/png", "本地上传", top=200, left=300),
            UploadTarget(9, "unknown", True, False, True, "image/jpeg,image/png", "本地上传", top=100, left=800),
            UploadTarget(10, "unknown", True, False, True, "image/jpeg,image/png", "元 元 本地上传 批量设置"),
            UploadTarget(11, "sku", True, False, True, "image/jpeg,image/png", "本地上传"),
        ]

        selected = color_sku_upload_targets(targets, expected_count=3)

        self.assertEqual([target.file_input_index for target in selected], [5, 9, 6])

    def test_clicks_first_existing_optional_button(self) -> None:
        class FakeButton:
            def __init__(self, exists: bool) -> None:
                self.exists = exists
                self.clicked = False

            def count(self) -> int:
                return 1 if self.exists else 0

            @property
            def first(self) -> "FakeButton":
                return self

            def click(self, timeout: int) -> None:
                self.clicked = True

        class FakePage:
            def __init__(self) -> None:
                self.buttons = {
                    "一键填充": FakeButton(False),
                    "一键复用": FakeButton(True),
                }
                self.waited = False

            def get_by_role(self, role: str, name: str) -> FakeButton:
                return self.buttons[name]

            def wait_for_timeout(self, timeout: int) -> None:
                self.waited = True

            def wait_for_function(self, expression: str, *, arg: object, timeout: int) -> None:
                return None

        page = FakePage()
        notes: list[str] = []

        click_first_optional_button(page, ("一键填充", "一键复用"), notes)

        self.assertTrue(page.buttons["一键复用"].clicked)
        self.assertTrue(page.waited)
        self.assertEqual(notes, ["clicked optional button: 一键复用"])


if __name__ == "__main__":
    unittest.main()

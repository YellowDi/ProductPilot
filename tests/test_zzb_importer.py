from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from importlib.util import find_spec
from pathlib import Path
from zipfile import ZipFile

if find_spec("openpyxl") is not None:
    from openpyxl import Workbook
else:
    Workbook = None  # type: ignore[assignment]

from product_pilot.app import validate_product_assets
from product_pilot.importers.xlsx import load_products_from_xlsx
from product_pilot.importers.zzb import (
    ZzbImportRequest,
    import_zzb_export,
    parse_zzb_sku_text,
)


class ZzbSkuTextTests(unittest.TestCase):
    def test_parses_zhizunbao_sku_text(self) -> None:
        rows = parse_zzb_sku_text(
            "\n".join(
                [
                    "颜色分类:黑色 鞋码:38 皮鞋尺码 价格： 146.64",
                    "颜色分类:白黑 鞋码:43 皮鞋尺码 价格： 146.64",
                ]
            )
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].color, "黑色")
        self.assertEqual(rows[0].size, "38")
        self.assertEqual(rows[0].price, Decimal("146.64"))
        self.assertEqual(rows[1].color, "白黑")
        self.assertEqual(rows[1].size, "43")


@unittest.skipUnless(Workbook is not None, "openpyxl is not installed")
class ZzbImportTests(unittest.TestCase):
    def test_imports_zip_export_to_standard_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            excel_path = root / "至尊宝_导出excel.xlsx"
            _write_zzb_workbook(excel_path)
            zip_path = root / "拼多多_商品ID_123456.zip"
            _write_media_zip(zip_path)
            output_path = root / "imports" / "123456" / "product-input.xlsx"

            result = import_zzb_export(
                ZzbImportRequest(
                    excel_path=excel_path,
                    sku_text="\n".join(
                        [
                            "颜色分类:黑色 鞋码:38 皮鞋尺码 价格： 146.64",
                            "颜色分类:黑色 鞋码:39 皮鞋尺码 价格： 146.64",
                        ]
                    ),
                    assets_path=zip_path,
                    title="测试男鞋",
                    category="流行男鞋 > 商务鞋 > 正装皮鞋",
                    output_path=output_path,
                )
            )

            self.assertTrue(output_path.exists())
            self.assertEqual(result.product.product_id, "123456")
            self.assertEqual(len(result.product.skus), 2)
            self.assertEqual([sku.stock for sku in result.product.skus], [198, 199])
            self.assertEqual(
                [(image.role, image.sku_attribute, image.sku_value) for image in result.product.images],
                [
                    ("main", "", ""),
                    ("detail", "", ""),
                    ("sku", "颜色分类", "黑色"),
                ],
            )

            product = load_products_from_xlsx(output_path)[0]
            self.assertEqual(product.validate(), [])
            self.assertEqual(validate_product_assets(product, output_path.parent), [])


def _write_zzb_workbook(path: Path) -> None:
    assert Workbook is not None
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "全部"
    sheet.append(["来源", "名称", "链接", "价格", "库存"])
    sheet.append(["主图", "主图01.jpg", "https://example.test/main.jpg", None, None])
    sheet.append(["SKU", "SKU01_黑色_38 皮鞋尺码.jpg", "https://example.test/sku.jpg", "146.64", 198])
    sheet.append(["SKU", "SKU02_黑色_39 皮鞋尺码.jpg", "https://example.test/sku.jpg", "146.64", 199])
    sheet.append(["详情图", "详情图01.jpg", "https://example.test/detail.jpg", None, None])
    workbook.save(path)


def _write_media_zip(path: Path) -> None:
    with ZipFile(path, "w") as zip_file:
        for name in (
            "拼多多_商品ID_123456/主图/主图01.jpg",
            "拼多多_商品ID_123456/SKU/SKU01_黑色_38 皮鞋尺码.jpg",
            "拼多多_商品ID_123456/SKU/SKU02_黑色_39 皮鞋尺码.jpg",
            "拼多多_商品ID_123456/详情图/详情图01.jpg",
        ):
            zip_file.writestr(name, b"test")


if __name__ == "__main__":
    unittest.main()

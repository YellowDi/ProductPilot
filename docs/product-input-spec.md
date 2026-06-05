# Product Input Spec

## Canonical Input

For delivery, ProductPilot accepts one product as one folder: an XLSX workbook plus local image files. JSON remains a developer/debug format and the internal normalized shape.

```text
products/
  SKU06/
    product-input.xlsx
    main.jpg
    detail-01.jpg
    detail-02.jpg
    sku.jpg
```

Image filenames inside the workbook are resolved relative to the directory containing the XLSX file. If a product later needs subfolders, `图片文件名` may also contain a relative path such as `detail/detail-01.jpg`.

## XLSX Workbook

The workbook requires three import sheets. Sheet and column names are fixed. Extra helper sheets such as `填写说明`, `商品属性`, and `SKU原始文本` are allowed and ignored by the importer.

### 商品

| 商品编号 | 商品标题 | 类目路径 | 商品描述 | 默认拼单价 | 默认单买价 | 默认参考价 | 默认库存 | 商品编码 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SKU06 | UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋 | 流行男鞋 > 低帮鞋 > 板鞋 | Optional internal note or future detail text. | 146.64 | 188 | 299 | 20 | demo001 |

### SKU

| 商品编号 | 颜色分类 | 鞋码 | SKU名称 | 拼单价 | 单买价 | 参考价 | 库存 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SKU06 | 黑色 | 38 |  |  |  |  |  |
|  | 黑色 | 39 |  |  |  |  |  |
|  | 棕色 | 38 |  |  |  |  |  |

For one-product workbooks, `商品编号` may be left blank in `SKU` and `图片` rows after the first row; ProductPilot treats blank values as the only product in the workbook. `SKU名称` may be left blank when `颜色分类` and/or `鞋码` are present; ProductPilot generates it from those attributes. Blank SKU price/stock cells inherit the matching `商品` default values. If both SKU stock and `默认库存` are blank, XLSX import uses `1000`.

### 图片

| 商品编号 | 图片角色 | 图片文件名 | SKU属性 | SKU值 |
| --- | --- | --- | --- | --- |
| SKU06 | main | main-01.jpg |  |  |
|  | main | main-02.jpg |  |  |
|  | detail | detail-01.jpg |  |  |
|  | detail | detail-02.jpg |  |  |
|  | sku | sku-black.jpg | 颜色分类 | 黑色 |
|  | sku | sku-brown.jpg | 颜色分类 | 棕色 |

`商品编号` is the join key across all three sheets. Do not merge cells or rename columns. Multiple main/detail/gallery images should use one row per image; upload order follows the row order in the `图片` sheet. For SKU images, bind one image to one SKU attribute value, such as `SKU属性=颜色分类` and `SKU值=黑色`; that image applies to all SKUs whose `颜色分类` is `黑色`.

English sheet names and headers are also accepted for developer fixtures:

- `Products`: `product_id`, `product_code`, `title`, `category`, `description`
- `SKUs`: `product_id`, `color`, `size`, `sku_name`, `price`, `single_price`, `reference_price`, `stock`
- `Images`: `product_id`, `image_role`, `image_path`, `sku_attribute`, `sku_value`

## JSON Debug Format

The equivalent single-product JSON bundle is:

```text
products/
  SKU06-json-debug/
    product.json
    images/
      main.jpg
      detail-01.jpg
      sku.jpg
```

`product.json` is the only machine-readable source for the automation flow. Image paths inside it are resolved relative to the directory containing `product.json`.

### JSON Shape

```json
{
  "product_id": "SKU06",
  "product_code": "demo001",
  "title": "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋",
  "category": "流行男鞋 > 低帮鞋 > 板鞋",
  "description": "Optional internal note or future detail text.",
  "images": [
    {
      "path": "images/main-01.jpg",
      "role": "main"
    },
    {
      "path": "images/main-02.jpg",
      "role": "main"
    },
    {
      "path": "images/detail-01.jpg",
      "role": "detail"
    },
    {
      "path": "images/sku-black.jpg",
      "role": "sku",
      "sku_attribute": "颜色分类",
      "sku_value": "黑色"
    }
  ],
  "skus": [
    {
      "name": "41",
      "price": "29.90",
      "single_price": "39.90",
      "reference_price": "99.00",
      "stock": 8
    }
  ]
}
```

## Field Rules

- `product_id` / `商品编号`: required in XLSX, optional in JSON. It identifies one product and joins SKU/image rows.
- `product_code` / `商品编码`: optional. Product spec attributes are handled by the backend `一键复用` action; current automation fills the product-level `商品编码` field separately in the price and inventory section.
- `title`: required, max 60 characters.
- `category`: required, use ` > ` between category levels.
- `description`: optional string. Current automation does not depend on it.
- `默认拼单价`, `默认单买价`, `默认参考价`, `默认库存`: optional product-level defaults used when matching SKU cells are blank. If XLSX SKU stock and `默认库存` are both blank, stock defaults to `1000`.
- `images`: required, at least one item with role `main`.
- `images[].path` / `图片文件名`: required filename or relative file path. Relative paths are resolved from the XLSX workbook directory or the `product.json` directory.
- `images[].role`: one of `main`, `gallery`, `detail`, `sku`.
- `SKU属性`, `SKU值`: optional for `sku` images, used to bind a SKU image to a structured SKU attribute value. If either is filled, both are required.
- `skus`: required, at least one SKU.
- `skus[].name` / `SKU名称`: required unless `颜色分类` or `鞋码` is filled.
- `颜色分类`, `鞋码`: optional structured SKU attributes. Use these for color-size SKU grids.
- `skus[].price`: required 拼单价, decimal string, greater than 0.
- `skus[].single_price`: optional 单买价, decimal string, greater than 0. Defaults to `price` in the current spike if omitted.
- `skus[].reference_price`: optional 划线价/参考价, decimal string, greater than the effective single price.
- `skus[].stock`: required integer, greater than or equal to 0. XLSX imports default blank stock to `1000`.

## Validation

Validate an XLSX input with:

```bash
python3 -B -m product_pilot.cli validate products/SKU06/product-input.xlsx
```

Validate a JSON debug bundle with:

```bash
python3 -B -m product_pilot.cli validate products/SKU06/product.json
```

The command checks workbook sheets and required columns, JSON structure for debug files, required fields, SKU prices and stock, image roles, and whether every declared image path exists as a file.

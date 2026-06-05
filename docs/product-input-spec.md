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

The workbook has three sheets. Sheet and column names are fixed.

### 商品

| 商品编号 | 商品标题 | 类目路径 | 商品描述 |
| --- | --- | --- | --- |
| SKU06 | UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋 | 流行男鞋 > 低帮鞋 > 板鞋 | Optional internal note or future detail text. |

### SKU

| 商品编号 | SKU名称 | 拼单价 | 单买价 | 参考价 | 库存 |
| --- | --- | --- | --- | --- | --- |
| SKU06 | 41 | 29.90 | 39.90 | 99.00 | 8 |
| SKU06 | 42 | 29.90 | 39.90 | 99.00 | 10 |

### 图片

| 商品编号 | 图片角色 | 图片文件名 |
| --- | --- | --- |
| SKU06 | main | main.jpg |
| SKU06 | detail | detail-01.jpg |
| SKU06 | detail | detail-02.jpg |
| SKU06 | sku | sku.jpg |

`商品编号` is the join key across all three sheets. Do not merge cells or rename columns. Multiple detail/gallery images should use one row per image; upload order follows the row order in the `图片` sheet.

English sheet names and headers are also accepted for developer fixtures:

- `Products`: `product_id`, `title`, `category`, `description`
- `SKUs`: `product_id`, `sku_name`, `price`, `single_price`, `reference_price`, `stock`
- `Images`: `product_id`, `image_role`, `image_path`

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
  "title": "UNITY优妮蒂男鞋低帮板鞋舒适休闲鞋",
  "category": "流行男鞋 > 低帮鞋 > 板鞋",
  "description": "Optional internal note or future detail text.",
  "images": [
    {
      "path": "images/main.jpg",
      "role": "main"
    },
    {
      "path": "images/detail-01.jpg",
      "role": "detail"
    },
    {
      "path": "images/sku.jpg",
      "role": "sku"
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
- `title`: required, max 60 characters.
- `category`: required, use ` > ` between category levels.
- `description`: optional string. Current automation does not depend on it.
- `images`: required, at least one item with role `main`.
- `images[].path` / `图片文件名`: required filename or relative file path. Relative paths are resolved from the XLSX workbook directory or the `product.json` directory.
- `images[].role`: one of `main`, `gallery`, `detail`, `sku`.
- `skus`: required, at least one SKU.
- `skus[].name`: required SKU option text, such as shoe size `41`.
- `skus[].price`: required 拼单价, decimal string, greater than 0.
- `skus[].single_price`: optional 单买价, decimal string, greater than 0. Defaults to `price` in the current spike if omitted.
- `skus[].reference_price`: optional 划线价/参考价, decimal string, greater than the effective single price.
- `skus[].stock`: required integer, greater than or equal to 0.

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

# ProductPilot

ProductPilot is a local desktop automation tool for preparing product listings in the Pinduoduo merchant backend.

The project does not use Pinduoduo Open Platform APIs. It automates Chrome/Chromium with Playwright, uses OCR only as auxiliary recognition, and keeps human control for login, captcha, risk checks, and final publish decisions.

## Current Stage

Stage 2: Playwright browser spike.

Implemented so far:

- Product draft validation.
- Persistent Chrome/Chromium profile launch configuration.
- Merchant backend login-state detection.
- Browser screenshot artifact output.
- Minimal PySide6 desktop shell for product validation, login check, and single-product draft runs.

## Product Validation

Install project dependencies first:

```bash
python3 -m pip install -e .
```

```bash
python3 -B -m product_pilot.cli validate examples/product.valid.json
```

The delivery product input is an XLSX workbook. JSON remains available as a developer/debug format. Both are documented in `docs/product-input-spec.md`.

A multi-SKU starter workbook is available at `examples/product-template/product-input-multisku.xlsx`.

## Zhizunbao Import

The desktop app can convert Zhizunbao exports into ProductPilot's standard workbook. Provide the exported Excel file,
paste the copied SKU text, and choose either the media zip or the extracted media folder. Zip files are extracted
automatically into the generated import directory.

The same conversion is available from the CLI:

```bash
python3 -B -m product_pilot.cli import-zzb \
  --excel test/至尊宝_导出excel.xlsx \
  --assets test/拼多多_商品ID_881133521557.zip \
  --sku-text-file sku.txt \
  --title "商品标题" \
  --category "流行男鞋 > 商务鞋 > 正装皮鞋"
```

The command writes `imports/<商品ID>/product-input.xlsx`, which can then be validated or used by `draft-spike`.

In the desktop app, each successful Zhizunbao import is added to the current batch table. Standard ProductPilot
JSON/XLSX files can also be added to the batch manually. Use `批量创建草稿` to process pending batch items in order.
The app creates or updates drafts only; final publish/submit remains a manual merchant-backend action.

## Browser Login Check

Install the browser automation dependency first:

```bash
python3 -m pip install -e '.[automation]'
python3 -m playwright install chromium
```

Open the merchant backend with a persistent profile:

```bash
python3 -m product_pilot.cli browser-check --hold
```

The `--hold` flag keeps the browser open so login, captcha, or risk checks can be completed manually. After pressing Enter in the terminal, the command checks whether the backend appears logged in and writes a screenshot under `artifacts/browser`.

## Publish Page Check

After login is persisted in the profile, open the product publish category page:

```bash
python3 -m product_pilot.cli publish-page-check
```

Use `--hold` when the page shows a slider, captcha, or other manual risk check:

```bash
python3 -m product_pilot.cli publish-page-check --hold
```

This command only detects page readiness and writes a screenshot. It does not upload images, fill product data, save drafts, or publish listings.

## Field Scan

Upload a test main image and scan visible fields:

```bash
python3 -m product_pilot.cli field-scan --main-image SKU06.jpg --keep-open
```

The default category is currently fixed to `流行男鞋 > 低帮鞋 > 板鞋`.

Advance to the product info page before scanning:

```bash
python3 -m product_pilot.cli field-scan --main-image SKU06.jpg --advance --keep-open
```

The command writes a screenshot and JSON scan result under `artifacts/browser`. It does not click save, submit, publish, or any final listing action.

## Draft Spike

Save the current test product to the draft box:

```bash
python3 -m product_pilot.cli draft-spike --product examples/product.sku06.json --keep-open
```

The product JSON provides the title, category, main image, detail image, SKU image, SKU sizes, stock, group price, single price, and reference price. CLI flags can still override individual values for one-off tests.

This command can click `保存草稿`. It never clicks `提交并上架`.

Verify field filling without saving:

```bash
python3 -m product_pilot.cli draft-spike --product examples/product.sku06.json --no-save --keep-open
```

## Desktop UI

Install the desktop optional dependency:

```bash
python3 -m pip install -e '.[desktop,automation]'
```

Start the desktop shell:

```bash
product-pilot-desktop
```

The first desktop MVP supports selecting a product JSON/XLSX file, validating product data, opening the merchant backend for manual login checks, and running the single-product draft spike. Batch task queues, resume support, and OCR diagnostics are planned for later stages.

## Desktop Packaging

Build packages on the target operating system. PyInstaller bundles Python and the installed Python dependencies, but it
does not bundle Chrome. The customer machine must have Chrome installed because ProductPilot launches Playwright with
the `chrome` channel.

macOS:

```bash
python3 -m pip install -e '.[desktop,automation,package]'
python3 scripts/build_desktop.py
```

Outputs:

- `release/darwin-<arch>/ProductPilot.app`
- `release/ProductPilot-darwin-<arch>.zip`

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[desktop,automation,package]"
.\.venv\Scripts\python scripts\build_desktop.py
```

Outputs:

- `release/windows-<arch>/ProductPilot/ProductPilot.exe`
- `release/ProductPilot-windows-<arch>.zip`

Windows `.exe` builds must be produced on Windows. macOS builds can be created on macOS. Unsigned demo builds may show
macOS Gatekeeper or Windows SmartScreen warnings after downloading; production delivery should add signing and
notarization.

## Quick Check

```bash
python3 -m unittest
python3 -m compileall product_pilot tests
```

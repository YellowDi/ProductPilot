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

## Product Validation

```bash
python3 -B -m product_pilot.cli validate examples/product.valid.json
```

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

## Quick Check

```bash
python3 -m unittest
python3 -m compileall product_pilot tests
```

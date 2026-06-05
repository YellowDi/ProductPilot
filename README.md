# ProductPilot

ProductPilot is a local desktop automation tool for preparing product listings in the Pinduoduo merchant backend.

The project does not use Pinduoduo Open Platform APIs. It automates Chrome/Chromium with Playwright, uses OCR only as auxiliary recognition, and keeps human control for login, captcha, risk checks, and final publish decisions.

## Current Stage

Stage 1: project skeleton and product draft validation.

## Quick Check

```bash
python3 -m unittest
python3 -m compileall product_pilot tests
```

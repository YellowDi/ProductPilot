"""Development CLI for ProductPilot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from product_pilot.domain.product import ProductDraft


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="product-pilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate a product draft JSON file.")
    validate_parser.add_argument("path", type=Path, help="Path to a product draft JSON file.")

    return parser


def validate_product(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"file not found: {path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"invalid json: {exc}", file=sys.stderr)
        return 2

    product = ProductDraft.from_mapping(payload)
    errors = product.validate()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print("ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return validate_product(args.path)

    raise AssertionError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

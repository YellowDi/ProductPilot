"""PySide6 desktop entry point."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError:
        print(
            "PySide6 is not installed. Install it with `python3 -m pip install -e '.[desktop]'`.",
            file=sys.stderr,
        )
        return 2

    from product_pilot.desktop.window import MainWindow

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

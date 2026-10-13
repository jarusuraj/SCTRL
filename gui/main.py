"""Application launcher for SCTRL GUI."""

from __future__ import annotations

import argparse
import sys

from sctrl.constants import APP_NAME, VERSION
from gui.client import DaemonClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sctrl-gui",
        description=f"{APP_NAME} Graphical Interface v{VERSION}",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run GUI with simulated mock backend",
    )
    parser.add_argument(
        "--tier",
        choices=["verified", "community", "detected", "unsupported", "bios_mismatch"],
        default="verified",
        help="Simulated tier in mock mode (default: verified)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        from PySide6.QtWidgets import QApplication
        from gui.main_window import MainWindow
    except ImportError:
        print("PySide6 is not installed. To run the graphical interface, install PySide6:")
        print("    pip install PySide6")
        print("\nAlternatively, use the command-line utility:")
        print("    python -m sctrl.cli status")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

    client = DaemonClient(force_mock=args.mock, mock_tier=args.tier)
    window = MainWindow(client)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

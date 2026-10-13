"""Diagnostics and hardware inspection view for SCTRL GUI."""

from __future__ import annotations

import json
from typing import Any

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:
    class DiagnosticsView(QWidget):
        """View displaying system identification, capability table, and raw JSON export."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(16)

            title = QLabel("System Diagnostics & Capability Map")
            title.setProperty("class", "title")
            layout.addWidget(title)

            # Info card
            info_card = QFrame()
            info_card.setProperty("class", "card")
            info_layout = QVBoxLayout(info_card)

            self.dmi_lbl = QLabel("Hardware: Loading...")
            self.dmi_lbl.setStyleSheet("font-weight: bold; color: #f0f6fc;")
            info_layout.addWidget(self.dmi_lbl)

            self.tier_lbl = QLabel("Support Tier: --")
            self.tier_lbl.setStyleSheet("color: #8b949e;")
            info_layout.addWidget(self.tier_lbl)

            layout.addWidget(info_card)

            # Capability Table
            self.table = QTableWidget(0, 5)
            self.table.setHorizontalHeaderLabels(["Feature", "Status", "Interface", "Read", "Write"])
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.table.setStyleSheet(
                "QTableWidget { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; }"
                "QHeaderView::section { background-color: #1f242c; color: #8b949e; padding: 6px; border: none; font-weight: bold; }"
            )
            layout.addWidget(self.table)

            # JSON export
            self.json_box = QTextEdit()
            self.json_box.setReadOnly(True)
            self.json_box.setMaximumHeight(150)
            self.json_box.setStyleSheet(
                "background-color: #0d1117; color: #8b949e; font-family: monospace; border: 1px solid #30363d; border-radius: 6px;"
            )
            layout.addWidget(self.json_box)

        def update_diagnostics(self, report: dict[str, Any]) -> None:
            dmi = report.get("dmi", {})
            model = dmi.get("product_name", "Unknown")
            board = dmi.get("board_name", "")
            bios = dmi.get("bios_version", "")
            self.dmi_lbl.setText(f"Hardware: {model} ({board}) | BIOS: {bios}")

            tier = report.get("tier", "unknown").upper()
            reason = report.get("tier_reason", "")
            self.tier_lbl.setText(f"Support Tier: {tier} - {reason}")

            caps = report.get("capabilities", [])
            self.table.setRowCount(len(caps))
            for row, cap in enumerate(caps):
                feat = QTableWidgetItem(str(cap.get("feature_id", "")))
                feat.setForeground(Qt.white)
                status = QTableWidgetItem(str(cap.get("status", "")))
                if cap.get("status") == "supported":
                    status.setForeground(Qt.green)
                else:
                    status.setForeground(Qt.yellow)
                iface = QTableWidgetItem(str(cap.get("interface", "")))
                r = QTableWidgetItem("Yes" if cap.get("readable") else "No")
                w = QTableWidgetItem("Yes" if cap.get("writable") else "No")

                self.table.setItem(row, 0, feat)
                self.table.setItem(row, 1, status)
                self.table.setItem(row, 2, iface)
                self.table.setItem(row, 3, r)
                self.table.setItem(row, 4, w)

            self.json_box.setPlainText(json.dumps(report, indent=2))
else:
    class DiagnosticsView:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

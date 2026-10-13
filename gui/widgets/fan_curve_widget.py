"""Interactive Fan Curve and mode selector widget for SCTRL GUI."""

from __future__ import annotations

from typing import Callable

try:
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtGui import QColor, QPainter, QPen, QBrush
    from PySide6.QtWidgets import (
        QButtonGroup,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSlider,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:
    class CurveCanvas(QWidget):
        """Visual 2D canvas plotting the temperature-to-speed fan curve."""

        def __init__(self, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self.setMinimumSize(400, 220)
            self._points = [(40, 25), (55, 45), (70, 70), (85, 95)]

        def set_points(self, points: list[tuple[int, int]]) -> None:
            self._points = points
            self.update()

        def paintEvent(self, event: Any) -> None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            w = self.width()
            h = self.height()
            margin = 35

            # Background
            painter.fillRect(0, 0, w, h, QColor("#161b22"))

            # Grid lines
            painter.setPen(QPen(QColor("#30363d"), 1, Qt.DashLine))
            for t in range(40, 101, 20):
                x = margin + (t - 30) / 70 * (w - 2 * margin)
                painter.drawLine(int(x), margin, int(x), h - margin)
                painter.drawText(int(x) - 10, h - 10, f"{t}°C")

            for s in range(0, 101, 25):
                y = (h - margin) - (s / 100 * (h - 2 * margin))
                painter.drawLine(margin, int(y), w - margin, int(y))
                painter.drawText(5, int(y) + 4, f"{s}%")

            # Plot curve line
            if len(self._points) >= 2:
                painter.setPen(QPen(QColor("#00e5ff"), 3))
                coords = []
                for t, s in self._points:
                    x = margin + (t - 30) / 70 * (w - 2 * margin)
                    y = (h - margin) - (s / 100 * (h - 2 * margin))
                    coords.append(QPointF(x, y))

                for i in range(len(coords) - 1):
                    painter.drawLine(coords[i], coords[i + 1])

                # Draw point handles
                painter.setBrush(QBrush(QColor("#ffffff")))
                painter.setPen(QPen(QColor("#00e5ff"), 2))
                for pt in coords:
                    painter.drawEllipse(pt, 5, 5)


    class FanControlView(QWidget):
        """Fan control panel with mode buttons (Auto, Max, Custom) and curve canvas."""

        def __init__(self, on_mode_change: Callable[[str], None] | None = None, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._on_mode_change = on_mode_change

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(16)

            # Header
            header_layout = QHBoxLayout()
            title = QLabel("Fan Control & Cooling")
            title.setProperty("class", "title")
            header_layout.addWidget(title)
            header_layout.addStretch()
            layout.addLayout(header_layout)

            # Mode selector buttons
            btn_box = QFrame()
            btn_box.setProperty("class", "card")
            btn_layout = QHBoxLayout(btn_box)

            self.btn_auto = QPushButton("Automatic (Firmware)")
            self.btn_auto.setCheckable(True)
            self.btn_auto.setChecked(True)
            self.btn_auto.clicked.connect(lambda: self._set_mode("auto"))

            self.btn_max = QPushButton("Maximum Cooling")
            self.btn_max.setCheckable(True)
            self.btn_max.clicked.connect(lambda: self._set_mode("max"))

            self.btn_custom = QPushButton("Custom Curve")
            self.btn_custom.setCheckable(True)
            self.btn_custom.clicked.connect(lambda: self._set_mode("custom"))

            self.btn_group = QButtonGroup(self)
            self.btn_group.addButton(self.btn_auto)
            self.btn_group.addButton(self.btn_max)
            self.btn_group.addButton(self.btn_custom)

            btn_layout.addWidget(self.btn_auto)
            btn_layout.addWidget(self.btn_max)
            btn_layout.addWidget(self.btn_custom)
            layout.addWidget(btn_box)

            # Curve section
            curve_card = QFrame()
            curve_card.setProperty("class", "card")
            curve_layout = QVBoxLayout(curve_card)

            curve_title = QLabel("CPU & GPU Thermal Curve")
            curve_title.setStyleSheet("font-weight: bold; color: #f0f6fc; margin-bottom: 8px;")
            curve_layout.addWidget(curve_title)

            self.canvas = CurveCanvas()
            curve_layout.addWidget(self.canvas)

            info_lbl = QLabel(
                "Lease Protection: Manual and custom fan modes require active lease renewal. "
                "If the control session expires or temperatures exceed critical thresholds, "
                "firmware automatic control is immediately restored."
            )
            info_lbl.setStyleSheet("color: #8b949e; font-size: 11px;")
            info_lbl.setWordWrap(True)
            curve_layout.addWidget(info_lbl)

            layout.addWidget(curve_card)

        def _set_mode(self, mode: str) -> None:
            if self._on_mode_change:
                self._on_mode_change(mode)

        def update_mode(self, mode: str) -> None:
            if mode == "auto":
                self.btn_auto.setChecked(True)
            elif mode == "max":
                self.btn_max.setChecked(True)
            elif mode == "custom":
                self.btn_custom.setChecked(True)
else:
    class FanControlView:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

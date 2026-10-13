"""Metric display cards for SCTRL GUI overview panel."""

from __future__ import annotations

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QHBoxLayout,
        QLabel,
        QProgressBar,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:
    class MetricCard(QFrame):
        """Card displaying a sensor value, unit, label, and progress gauge."""

        def __init__(
            self,
            title: str,
            unit: str = "",
            max_val: float = 100.0,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self.setProperty("class", "card")
            self._unit = unit
            self._max_val = max_val

            layout = QVBoxLayout(self)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(8)

            # Header label
            self.title_lbl = QLabel(title)
            self.title_lbl.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: bold; text-transform: uppercase;")
            layout.addWidget(self.title_lbl)

            # Value label
            self.val_lbl = QLabel("--")
            self.val_lbl.setProperty("class", "metric-val")
            self.val_lbl.setStyleSheet("font-size: 28px; font-weight: bold; color: #f0f6fc;")
            layout.addWidget(self.val_lbl)

            # Progress bar
            self.bar = QProgressBar()
            self.bar.setTextVisible(False)
            self.bar.setRange(0, int(max_val))
            self.bar.setValue(0)
            self.bar.setFixedHeight(6)
            layout.addWidget(self.bar)

        def update_value(self, val: float | None, status_color: str | None = None) -> None:
            if val is None:
                self.val_lbl.setText("--")
                self.bar.setValue(0)
            else:
                if self._unit == "RPM":
                    self.val_lbl.setText(f"{int(val)} {self._unit}")
                elif self._unit == "B":
                    gb = val / (1024 ** 3)
                    self.val_lbl.setText(f"{gb:.1f} GB")
                else:
                    self.val_lbl.setText(f"{val:.1f} {self._unit}")

                self.bar.setValue(min(int(val), int(self._max_val)))

                if status_color:
                    self.bar.setStyleSheet(f"QProgressBar::chunk {{ background-color: {status_color}; border-radius: 3px; }}")
else:
    class MetricCard:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

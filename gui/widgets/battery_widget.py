"""Battery charge limit and health widget for SCTRL GUI."""

from __future__ import annotations

from typing import Callable

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSlider,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:
    class BatteryView(QWidget):
        """Battery health and charge threshold control view."""

        def __init__(
            self,
            on_limit_change: Callable[[int], None] | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._on_limit_change = on_limit_change

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(16)

            # Title
            title = QLabel("Battery Health & Charging Limit")
            title.setProperty("class", "title")
            layout.addWidget(title)

            # Card
            card = QFrame()
            card.setProperty("class", "card")
            card_layout = QVBoxLayout(card)
            card_layout.setSpacing(12)

            self.status_lbl = QLabel("Battery Status: Discharging (72%)")
            self.status_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #f0f6fc;")
            card_layout.addWidget(self.status_lbl)

            desc = QLabel(
                "Limiting maximum battery charge to 80% substantially extends lithium-ion battery "
                "longevity by avoiding high cell voltage stress during prolonged AC adapter usage."
            )
            desc.setStyleSheet("color: #8b949e; line-height: 1.4;")
            desc.setWordWrap(True)
            card_layout.addWidget(desc)

            # Limit controls
            ctrl_layout = QHBoxLayout()
            self.limit_lbl = QLabel("Charge Threshold: 80%")
            self.limit_lbl.setStyleSheet("font-weight: bold; color: #00e5ff;")
            ctrl_layout.addWidget(self.limit_lbl)
            ctrl_layout.addStretch()
            card_layout.addLayout(ctrl_layout)

            self.slider = QSlider(Qt.Horizontal)
            self.slider.setRange(50, 100)
            self.slider.setValue(80)
            self.slider.valueChanged.connect(self._on_slider_changed)
            card_layout.addWidget(self.slider)

            btn_layout = QHBoxLayout()
            self.btn_80 = QPushButton("Set 80% (Recommended)")
            self.btn_80.clicked.connect(lambda: self._set_limit(80))
            self.btn_100 = QPushButton("Set 100% (Full Capacity)")
            self.btn_100.clicked.connect(lambda: self._set_limit(100))

            btn_layout.addWidget(self.btn_80)
            btn_layout.addWidget(self.btn_100)
            btn_layout.addStretch()
            card_layout.addLayout(btn_layout)

            layout.addWidget(card)
            layout.addStretch()

        def _on_slider_changed(self, val: int) -> None:
            self.limit_lbl.setText(f"Charge Threshold: {val}%")

        def _set_limit(self, val: int) -> None:
            self.slider.setValue(val)
            if self._on_limit_change:
                self._on_limit_change(val)

        def update_battery(self, percent: float | None, state: str, limit: int | None) -> None:
            pct_str = f"{int(percent)}%" if percent is not None else "--"
            self.status_lbl.setText(f"Battery Status: {state.capitalize()} ({pct_str})")
            if limit is not None:
                self.slider.setValue(limit)
                self.limit_lbl.setText(f"Charge Threshold: {limit}%")
else:
    class BatteryView:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

"""Keyboard lighting and RGB zones view for SCTRL GUI."""

from __future__ import annotations

from typing import Callable

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QColorDialog,
        QComboBox,
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
    class KeyboardLightingView(QWidget):
        """Keyboard backlight brightness and multi-zone RGB controls."""

        def __init__(
            self,
            on_brightness: Callable[[int], None] | None = None,
            on_color: Callable[[int, int, int, int], None] | None = None,
            on_effect: Callable[[str, int], None] | None = None,
            parent: QWidget | None = None,
        ) -> None:
            super().__init__(parent)
            self._on_brightness = on_brightness
            self._on_color = on_color
            self._on_effect = on_effect

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(16)

            title = QLabel("Keyboard Lighting & Backlight")
            title.setProperty("class", "title")
            layout.addWidget(title)

            # Brightness card
            b_card = QFrame()
            b_card.setProperty("class", "card")
            b_layout = QVBoxLayout(b_card)

            b_title = QLabel("Backlight Brightness")
            b_title.setStyleSheet("font-weight: bold; color: #f0f6fc;")
            b_layout.addWidget(b_title)

            self.b_slider = QSlider(Qt.Horizontal)
            self.b_slider.setRange(0, 100)
            self.b_slider.setValue(100)
            self.b_slider.valueChanged.connect(self._on_b_change)
            b_layout.addWidget(self.b_slider)
            layout.addWidget(b_card)

            # RGB zones card
            rgb_card = QFrame()
            rgb_card.setProperty("class", "card")
            rgb_layout = QVBoxLayout(rgb_card)

            rgb_title = QLabel("4-Zone RGB Backlight")
            rgb_title.setStyleSheet("font-weight: bold; color: #f0f6fc;")
            rgb_layout.addWidget(rgb_title)

            zones_layout = QHBoxLayout()
            self.zone_btns = []
            for z in range(4):
                btn = QPushButton(f"Zone {z + 1}")
                btn.setStyleSheet("background-color: #0078d4; color: white; padding: 12px; border-radius: 6px; font-weight: bold;")
                btn.clicked.connect(lambda checked=False, zone=z: self._pick_color(zone))
                self.zone_btns.append(btn)
                zones_layout.addWidget(btn)
            rgb_layout.addLayout(zones_layout)

            # Effects
            eff_layout = QHBoxLayout()
            eff_lbl = QLabel("Effect:")
            eff_lbl.setStyleSheet("color: #8b949e;")
            self.eff_combo = QComboBox()
            self.eff_combo.addItems(["static", "breathing", "off"])
            self.eff_combo.currentTextChanged.connect(self._on_eff_change)

            eff_layout.addWidget(eff_lbl)
            eff_layout.addWidget(self.eff_combo)
            eff_layout.addStretch()
            rgb_layout.addLayout(eff_layout)

            layout.addWidget(rgb_card)
            layout.addStretch()

        def _on_b_change(self, val: int) -> None:
            if self._on_brightness:
                self._on_brightness(val)

        def _pick_color(self, zone: int) -> None:
            color = QColorDialog.getColor()
            if color.isValid():
                r, g, b = color.red(), color.green(), color.blue()
                self.zone_btns[zone].setStyleSheet(f"background-color: rgb({r},{g},{b}); color: white; padding: 12px; border-radius: 6px; font-weight: bold;")
                if self._on_color:
                    self._on_color(zone, r, g, b)

        def _on_eff_change(self, effect: str) -> None:
            if self._on_effect:
                self._on_effect(effect, 50)
else:
    class KeyboardLightingView:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

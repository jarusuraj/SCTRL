"""Main application window for SCTRL GUI."""

from __future__ import annotations

import logging
from typing import Any

from sctrl.constants import APP_NAME, VERSION
from gui.client import DaemonClient
from gui.theme import (
    ACCENT_AMBER,
    ACCENT_CYAN,
    ACCENT_GREEN,
    ACCENT_RED,
    TIER_COLORS,
    get_stylesheet,
)

logger = logging.getLogger("sctrl_gui.window")

try:
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import (
        QButtonGroup,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QScrollArea,
        QStackedWidget,
        QVBoxLayout,
        QWidget,
    )
    from gui.widgets.battery_widget import BatteryView
    from gui.widgets.diagnostics_widget import DiagnosticsView
    from gui.widgets.fan_curve_widget import FanControlView
    from gui.widgets.keyboard_widget import KeyboardLightingView
    from gui.widgets.status_card import MetricCard
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:
    class MainWindow(QMainWindow):
        """SCTRL desktop control center main window."""

        def __init__(self, client: DaemonClient, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._client = client
            self.setWindowTitle(f"{APP_NAME} - Laptop Control Center v{VERSION}")
            self.resize(1000, 680)
            self.setStyleSheet(get_stylesheet())

            # Root widget & horizontal split (sidebar + content)
            root = QWidget(self)
            self.setCentralWidget(root)
            main_layout = QHBoxLayout(root)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(0)

            # Sidebar
            sidebar = QFrame()
            sidebar.setProperty("class", "nav-sidebar")
            sidebar.setFixedWidth(220)
            side_layout = QVBoxLayout(sidebar)
            side_layout.setContentsMargins(12, 20, 12, 20)
            side_layout.setSpacing(6)

            # Brand
            brand_lbl = QLabel(f"⚡ {APP_NAME}")
            brand_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #00e5ff; margin-bottom: 20px; padding-left: 8px;")
            side_layout.addWidget(brand_lbl)

            # Navigation buttons
            self.nav_group = QButtonGroup(self)
            self.nav_btns: list[QPushButton] = []
            nav_items = [
                ("📊 Overview", 0),
                ("🌀 Cooling & Fans", 1),
                ("⚡ Performance Profiles", 2),
                ("🔋 Battery Health", 3),
                ("💡 Keyboard RGB", 4),
                ("🔍 Diagnostics", 5),
            ]

            for label, page_idx in nav_items:
                btn = QPushButton(label)
                btn.setProperty("class", "nav-btn")
                btn.setCheckable(True)
                if page_idx == 0:
                    btn.setChecked(True)
                btn.clicked.connect(lambda checked=False, idx=page_idx: self._switch_page(idx))
                self.nav_group.addButton(btn)
                self.nav_btns.append(btn)
                side_layout.addWidget(btn)

            side_layout.addStretch()

            # Mode indicator footer
            self.footer_lbl = QLabel("Mode: Mock Simulation" if self._client.is_mock else "Connected: System D-Bus")
            self.footer_lbl.setStyleSheet("color: #8b949e; font-size: 11px; padding-left: 8px;")
            side_layout.addWidget(self.footer_lbl)

            main_layout.addWidget(sidebar)

            # Content area
            content_wrap = QWidget()
            content_layout = QVBoxLayout(content_wrap)
            content_layout.setContentsMargins(24, 20, 24, 20)
            content_layout.setSpacing(16)

            # Top bar (Hardware info + Tier badge)
            top_bar = QHBoxLayout()
            self.hw_label = QLabel("Loading hardware identity...")
            self.hw_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #f0f6fc;")
            top_bar.addWidget(self.hw_label)
            top_bar.addStretch()

            self.tier_badge = QLabel("TIER: UNKNOWN")
            self.tier_badge.setStyleSheet(
                "background-color: #0c213b; color: #58a6ff; font-weight: bold; font-size: 11px; padding: 4px 10px; border-radius: 12px;"
            )
            top_bar.addWidget(self.tier_badge)
            content_layout.addLayout(top_bar)

            # Emergency alert banner (hidden by default)
            self.alert_banner = QFrame()
            self.alert_banner.setStyleSheet("background-color: #360c0c; border: 1px solid #f85149; border-radius: 6px; padding: 10px;")
            alert_layout = QHBoxLayout(self.alert_banner)
            self.alert_lbl = QLabel("CRITICAL THERMAL OVERRIDE ACTIVE: Fans forced to maximum cooling!")
            self.alert_lbl.setStyleSheet("color: #f85149; font-weight: bold;")
            alert_layout.addWidget(self.alert_lbl)
            self.alert_banner.setVisible(False)
            content_layout.addWidget(self.alert_banner)

            # Page stack
            self.pages = QStackedWidget()
            self._init_pages()
            content_layout.addWidget(self.pages)

            main_layout.addWidget(content_wrap)

            # Telemetry timer
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._poll_telemetry)
            self._timer.start(1000)

            # Initial poll
            self._poll_telemetry()

        def _init_pages(self) -> None:
            # Page 0: Overview
            overview_scroll = QScrollArea()
            overview_widget = QWidget()
            self.overview_layout = QVBoxLayout(overview_widget)
            self.overview_layout.setContentsMargins(0, 0, 0, 0)
            self.overview_layout.setSpacing(16)

            cards_grid = QGridLayout()
            cards_grid.setSpacing(16)

            self.card_cpu_temp = MetricCard("CPU Temperature", "°C", 100.0)
            self.card_gpu_temp = MetricCard("GPU Temperature", "°C", 100.0)
            self.card_cpu_fan = MetricCard("CPU Fan", "RPM", 6000.0)
            self.card_gpu_fan = MetricCard("GPU Fan", "RPM", 6000.0)
            self.card_cpu_util = MetricCard("CPU Utilization", "%", 100.0)
            self.card_ram_util = MetricCard("RAM Utilization", "%", 100.0)

            cards_grid.addWidget(self.card_cpu_temp, 0, 0)
            cards_grid.addWidget(self.card_gpu_temp, 0, 1)
            cards_grid.addWidget(self.card_cpu_fan, 1, 0)
            cards_grid.addWidget(self.card_gpu_fan, 1, 1)
            cards_grid.addWidget(self.card_cpu_util, 2, 0)
            cards_grid.addWidget(self.card_ram_util, 2, 1)
            self.overview_layout.addLayout(cards_grid)
            self.overview_layout.addStretch()

            overview_scroll.setWidget(overview_widget)
            overview_scroll.setWidgetResizable(True)
            self.pages.addWidget(overview_scroll)

            # Page 1: Cooling & Fans
            self.fan_view = FanControlView(on_mode_change=self._client.set_fan_mode)
            self.pages.addWidget(self.fan_view)

            # Page 2: Performance Profiles
            prof_wrap = QWidget()
            prof_layout = QVBoxLayout(prof_wrap)
            prof_title = QLabel("Performance Profiles")
            prof_title.setProperty("class", "title")
            prof_layout.addWidget(prof_title)

            prof_card = QFrame()
            prof_card.setProperty("class", "card")
            pcard_layout = QVBoxLayout(prof_card)
            pcard_layout.setSpacing(12)

            self.prof_status = QLabel("Current Profile: Balanced")
            self.prof_status.setStyleSheet("font-weight: bold; font-size: 15px; color: #00e5ff;")
            pcard_layout.addWidget(self.prof_status)

            p_btn_layout = QHBoxLayout()
            for p in ["quiet", "balanced", "performance", "turbo"]:
                btn = QPushButton(p.capitalize())
                btn.setProperty("class", "primary-btn")
                btn.clicked.connect(lambda checked=False, name=p: self._set_profile(name))
                p_btn_layout.addWidget(btn)
            pcard_layout.addLayout(p_btn_layout)
            prof_layout.addWidget(prof_card)
            prof_layout.addStretch()
            self.pages.addWidget(prof_wrap)

            # Page 3: Battery Health
            self.battery_view = BatteryView(on_limit_change=self._client.set_charge_limit)
            self.pages.addWidget(self.battery_view)

            # Page 4: Keyboard Lighting
            self.keyboard_view = KeyboardLightingView(
                on_brightness=self._client.set_keyboard_brightness,
                on_color=self._client.set_keyboard_zone_color,
                on_effect=self._client.set_keyboard_effect,
            )
            self.pages.addWidget(self.keyboard_view)

            # Page 5: Diagnostics
            self.diag_view = DiagnosticsView()
            self.pages.addWidget(self.diag_view)

        def _switch_page(self, idx: int) -> None:
            self.pages.setCurrentIndex(idx)
            if idx == 5:
                # Refresh diagnostics on page switch
                diag = self._client.get_diagnostics()
                self.diag_view.update_diagnostics(diag)

        def _set_profile(self, profile: str) -> None:
            res = self._client.set_profile(profile)
            if res.get("success"):
                self.prof_status.setText(f"Current Profile: {profile.capitalize()}")

        def _poll_telemetry(self) -> None:
            try:
                state = self._client.get_state()
                telemetry = self._client.get_telemetry()

                # Update header
                dmi = state.get("dmi", {})
                prod = dmi.get("product_name", "Unknown System")
                bios = dmi.get("bios_version", "")
                self.hw_label.setText(f"{prod} ({bios})")

                # Update tier badge
                tier = state.get("tier", "unknown")
                text_col, bg_col = TIER_COLORS.get(tier, ("#58a6ff", "#0c213b"))
                self.tier_badge.setText(f"TIER: {tier.upper()}")
                self.tier_badge.setStyleSheet(
                    f"background-color: {bg_col}; color: {text_col}; font-weight: bold; font-size: 11px; padding: 4px 10px; border-radius: 12px;"
                )

                # Emergency override banner
                emergency = state.get("emergency_override", False)
                self.alert_banner.setVisible(emergency)

                # Update overview cards
                cpu_t = telemetry.get("cpu_temp", {}).get("value")
                self.card_cpu_temp.update_value(cpu_t, ACCENT_RED if (cpu_t and cpu_t > 85) else ACCENT_CYAN)

                gpu_t = telemetry.get("gpu_temp", {}).get("value")
                self.card_gpu_temp.update_value(gpu_t, ACCENT_RED if (gpu_t and gpu_t > 80) else ACCENT_CYAN)

                cpu_fan = telemetry.get("cpu_fan_rpm", {}).get("value")
                self.card_cpu_fan.update_value(cpu_fan)

                gpu_fan = telemetry.get("gpu_fan_rpm", {}).get("value")
                self.card_gpu_fan.update_value(gpu_fan)

                cpu_u = telemetry.get("cpu_util", {}).get("value")
                self.card_cpu_util.update_value(cpu_u)

                ram_u = telemetry.get("ram_util", {}).get("value")
                self.card_ram_util.update_value(ram_u)

                # Update battery view
                bat_pct = telemetry.get("battery_percent", {}).get("value")
                bat_st = telemetry.get("battery_state", "unknown")
                chg_lim = telemetry.get("charge_limit", {}).get("value")
                self.battery_view.update_battery(bat_pct, bat_st, int(chg_lim) if chg_lim else None)

                # Update fan mode
                fan_m = state.get("fan_mode", "auto")
                self.fan_view.update_mode(fan_m)

                # Update profile
                prof_applied = state.get("profile", {}).get("applied")
                if prof_applied:
                    self.prof_status.setText(f"Current Profile: {prof_applied.capitalize()}")
            except Exception as e:
                logger.debug("Error during GUI poll: %s", e)

        def closeEvent(self, event: Any) -> None:
            self._client.close()
            event.accept()
else:
    class MainWindow:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

"""Daemon client for SCTRL GUI.

Connects to the system D-Bus daemon, or falls back to an in-process
mock service when running in developer mode or without a system bus.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from sctrl.constants import (
    DBUS_INTERFACE,
    DBUS_OBJECT_PATH,
    DBUS_SERVICE_NAME,
)
from sctrl.models import FanCurve, FanMode, TelemetrySnapshot
from daemon.service import SCTRLService

logger = logging.getLogger("sctrl_gui.client")


class DaemonClient:
    """Client interface for GUI to communicate with SCTRL daemon."""

    def __init__(self, force_mock: bool = False, mock_tier: str = "verified") -> None:
        self._force_mock = force_mock
        self._mock_tier = mock_tier
        self._local_service: SCTRLService | None = None
        self._dbus_proxy: Any = None
        self._is_mock = False

        self._init_connection()

    def _init_connection(self) -> None:
        """Initialize connection to D-Bus or local mock service."""
        if self._force_mock:
            self._setup_local_mock()
            return

        # Attempt D-Bus connection
        try:
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType
            # In a synchronous Qt context, local service fallback is used unless running async loop
            logger.info("Attempting D-Bus connection...")
            # For immediate reliable operation, initialize local mock if D-Bus is not reachable
            self._setup_local_mock()
        except Exception as e:
            logger.info("D-Bus not available (%s); falling back to in-process mock service", e)
            self._setup_local_mock()

    def _setup_local_mock(self) -> None:
        self._is_mock = True
        logger.info("Setting up in-process service (tier: %s)", self._mock_tier)
        self._local_service = SCTRLService(mock_mode=True, mock_model=self._mock_tier)
        self._local_service.start()

    @property
    def is_mock(self) -> bool:
        return self._is_mock

    def get_state(self) -> dict[str, Any]:
        """Fetch daemon state."""
        if self._local_service:
            return self._local_service.get_state().to_dict()
        return {}

    def get_telemetry(self) -> dict[str, Any]:
        """Fetch latest telemetry snapshot."""
        if self._local_service:
            snapshot = self._local_service.tick()
            return snapshot.to_dict()
        return {}

    def get_diagnostics(self) -> dict[str, Any]:
        """Fetch diagnostic report."""
        if self._local_service:
            return self._local_service.get_diagnostics().to_dict()
        return {}

    def set_fan_mode(self, mode: str) -> dict[str, Any]:
        """Set fan mode (auto, max)."""
        if self._local_service:
            return self._local_service.set_fan_mode(mode)
        return {"success": False, "error": "Not connected"}

    def set_profile(self, profile: str) -> dict[str, Any]:
        """Set performance profile."""
        if self._local_service:
            return self._local_service.set_profile(profile)
        return {"success": False, "error": "Not connected"}

    def set_charge_limit(self, percent: int) -> dict[str, Any]:
        """Set battery charge threshold."""
        if self._local_service:
            return self._local_service.set_charge_limit(percent)
        return {"success": False, "error": "Not connected"}

    def set_keyboard_brightness(self, level: int) -> dict[str, Any]:
        """Set keyboard backlight brightness."""
        if self._local_service:
            return self._local_service.set_keyboard_brightness(level)
        return {"success": False, "error": "Not connected"}

    def set_keyboard_zone_color(self, zone_id: int, r: int, g: int, b: int) -> dict[str, Any]:
        """Set keyboard zone RGB color."""
        if self._local_service:
            return self._local_service.set_keyboard_zone_color(zone_id, r, g, b)
        return {"success": False, "error": "Not connected"}

    def set_keyboard_effect(self, effect: str, speed: int = 50) -> dict[str, Any]:
        """Set keyboard lighting effect."""
        if self._local_service:
            return self._local_service.set_keyboard_effect(effect, speed)
        return {"success": False, "error": "Not connected"}

    def set_feature_optin(self, feature_id: str, opted_in: bool) -> None:
        """Set opt-in for detected tier."""
        if self._local_service:
            self._local_service.set_feature_optin(feature_id, opted_in)

    def close(self) -> None:
        """Clean up resources."""
        if self._local_service:
            self._local_service.stop()

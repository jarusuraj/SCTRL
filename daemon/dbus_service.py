"""D-Bus service interface for SCTRL daemon.

Exports org.sctrl.Daemon on the system bus (or session bus in user/dev mode).
Provides async D-Bus methods, signals, and polkit authorization checks.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sctrl.constants import (
    DBUS_INTERFACE,
    DBUS_OBJECT_PATH,
    DBUS_SERVICE_NAME,
)
from sctrl.models import FanCurve, FanCurvePoint, TelemetrySnapshot
from daemon.control.thermal_policy import ThermalAlert
from daemon.service import SCTRLService

logger = logging.getLogger("sctrld.dbus")

try:
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, dbus_property, method, signal
    _HAS_DBUS = True
except ImportError:
    _HAS_DBUS = False


if _HAS_DBUS:
    class SCTRLDBusInterface(ServiceInterface):
        """D-Bus interface export for org.sctrl.Daemon."""

        def __init__(self, service: SCTRLService) -> None:
            super().__init__(DBUS_INTERFACE)
            self._service = service

            # Subscribe to service events
            self._service.subscribe_telemetry(self._on_telemetry)
            self._service.subscribe_alert(self._on_alert)

        def _on_telemetry(self, snapshot: TelemetrySnapshot) -> None:
            try:
                data_json = json.dumps(snapshot.to_dict())
                self.TelemetryUpdated(data_json)
            except Exception as e:
                logger.debug("Failed emitting TelemetryUpdated: %s", e)

        def _on_alert(self, alert: ThermalAlert) -> None:
            try:
                data_json = json.dumps(alert.to_dict())
                self.ThermalAlert(data_json)
            except Exception as e:
                logger.debug("Failed emitting ThermalAlert: %s", e)

        # Signals
        @signal()
        def TelemetryUpdated(self, snapshot_json: "s") -> "s":
            return snapshot_json

        @signal()
        def ThermalAlert(self, alert_json: "s") -> "s":
            return alert_json

        @signal()
        def StateChanged(self, state_json: "s") -> "s":
            return state_json

        # Methods
        @method()
        def GetState(self) -> "s":
            """Return overall daemon state as JSON."""
            return json.dumps(self._service.get_state().to_dict())

        @method()
        def GetTelemetry(self) -> "s":
            """Return latest telemetry snapshot as JSON."""
            return json.dumps(self._service.get_telemetry().to_dict())

        @method()
        def GetCapabilities(self) -> "s":
            """Return discovered capabilities list as JSON."""
            return json.dumps(self._service.get_capabilities())

        @method()
        def GetDiagnostics(self) -> "s":
            """Return full diagnostic report as JSON."""
            return json.dumps(self._service.get_diagnostics().to_dict())

        @method()
        def SetFanMode(self, mode: "s", holder: "s") -> "s":
            """Set fan mode (auto, max)."""
            res = self._service.set_fan_mode(mode, holder)
            return json.dumps(res)

        @method()
        def SetCustomCurve(self, holder: "s", curve_json: "s") -> "s":
            """Apply custom fan curve JSON."""
            data = json.loads(curve_json)
            cpu_points = [FanCurvePoint(p["temp_c"], p["speed_percent"]) for p in data.get("cpu_points", [])]
            gpu_points = [FanCurvePoint(p["temp_c"], p["speed_percent"]) for p in data.get("gpu_points", [])]
            cpu_curve = FanCurve(points=cpu_points) if cpu_points else None
            gpu_curve = FanCurve(points=gpu_points) if gpu_points else None

            res = self._service.set_custom_curve(holder, cpu_curve, gpu_curve)
            return json.dumps(res)

        @method()
        def RenewFanLease(self, holder: "s", duration_s: "i") -> "b":
            """Renew active fan control lease."""
            return self._service.renew_fan_lease(holder, duration_s)

        @method()
        def SetProfile(self, profile: "s") -> "s":
            """Set performance profile."""
            res = self._service.set_profile(profile)
            return json.dumps(res)

        @method()
        def SetChargeLimit(self, percent: "i") -> "s":
            """Set battery charge limit percentage."""
            res = self._service.set_charge_limit(percent)
            return json.dumps(res)

        @method()
        def SetKeyboardBrightness(self, level: "i") -> "s":
            """Set keyboard brightness level (0-100)."""
            res = self._service.set_keyboard_brightness(level)
            return json.dumps(res)

        @method()
        def SetKeyboardZoneColor(self, zone_id: "i", r: "i", g: "i", b: "i") -> "s":
            """Set keyboard RGB zone color."""
            res = self._service.set_keyboard_zone_color(zone_id, r, g, b)
            return json.dumps(res)

        @method()
        def SetKeyboardEffect(self, effect: "s", speed: "i") -> "s":
            """Set keyboard animation effect and speed."""
            res = self._service.set_keyboard_effect(effect, speed)
            return json.dumps(res)

        @method()
        def SetFeatureOptIn(self, feature_id: "s", opted_in: "b") -> "b":
            """Set opt-in for detected tier writes."""
            self._service.set_feature_optin(feature_id, opted_in)
            return True


class DBusServer:
    """Manages D-Bus connection and lifecycle."""

    def __init__(self, service: SCTRLService, use_session_bus: bool = False) -> None:
        self._service = service
        self._use_session_bus = use_session_bus
        self._bus: MessageBus | None = None
        self._interface: SCTRLDBusInterface | None = None

    async def start(self) -> None:
        if not _HAS_DBUS:
            logger.warning("dbus-next is not installed; D-Bus server disabled")
            return

        try:
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType

            bus_type = BusType.SESSION if self._use_session_bus else BusType.SYSTEM
            self._bus = await MessageBus(bus_type=bus_type).connect()

            self._interface = SCTRLDBusInterface(self._service)
            self._bus.export(DBUS_OBJECT_PATH, self._interface)

            reply = await self._bus.request_name(DBUS_SERVICE_NAME)
            logger.info("D-Bus service %s exported on %s (result: %s)", DBUS_SERVICE_NAME, bus_type.name, reply)
        except Exception as e:
            logger.warning("Failed to connect or export on D-Bus: %s", e)

    async def stop(self) -> None:
        if self._bus:
            self._bus.disconnect()
            logger.info("Disconnected from D-Bus")

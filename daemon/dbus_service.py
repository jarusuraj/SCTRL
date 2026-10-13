"""D-Bus service interface for SCTRL daemon.

Exports io.github.sctrl.sctrl.Control on the system bus (or session bus in user/dev mode).
Provides async D-Bus methods, signals, polkit authorization checks, and rate limiting.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import time
from typing import Any

from sctrl.constants import (
    DBUS_INTERFACE,
    DBUS_OBJECT_PATH,
    DBUS_RATE_LIMIT_PER_S,
    DBUS_SERVICE_NAME,
    POLKIT_ACTION_ADMIN,
    POLKIT_ACTION_WRITE,
)
from sctrl.errors import ErrorCode, PermissionDeniedError
from sctrl.models import FanCurve, FanCurvePoint, TelemetrySnapshot
from daemon.control.thermal_policy import ThermalAlert
from daemon.service import SCTRLService

logger = logging.getLogger("sctrld.dbus")

# Context variable tracking current D-Bus caller sender
current_sender_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_sender_var", default="local"
)

try:
    from dbus_next import Message, MessageType, Variant
    from dbus_next.aio import MessageBus
    from dbus_next.service import ServiceInterface, method, signal
    _HAS_DBUS = True
except ImportError:
    _HAS_DBUS = False
    # Mock base class when dbus-next is not installed
    class ServiceInterface:  # type: ignore[no-redef]
        def __init__(self, name: str) -> None:
            self.name = name

    def method(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        def decorator(fn: Any) -> Any:
            return fn
        return decorator

    def signal(*args: Any, **kwargs: Any) -> Any:  # type: ignore[no-redef]
        def decorator(fn: Any) -> Any:
            return fn
        return decorator


class RateLimiter:
    """Sliding-window per-sender rate limiter."""

    def __init__(self, max_per_second: int = DBUS_RATE_LIMIT_PER_S) -> None:
        self.max_per_second = max_per_second
        self._history: dict[str, list[float]] = {}

    def check(self, sender: str, now: float | None = None) -> None:
        t = now if now is not None else time.monotonic()
        history = self._history.setdefault(sender, [])
        # Prune calls older than 1 second
        cutoff = t - 1.0
        self._history[sender] = [call_time for call_time in history if call_time > cutoff]
        if len(self._history[sender]) >= self.max_per_second:
            raise PermissionDeniedError(
                f"Rate limit exceeded (max {self.max_per_second} calls/s)",
                code=ErrorCode.RATE_LIMITED,
            )
        self._history[sender].append(t)


class PolkitAuthorizer:
    """Authority client verifying caller authorization via Polkit."""

    def __init__(self, bus: Any = None, enabled: bool = True) -> None:
        self._bus = bus
        self._enabled = enabled

    def set_bus(self, bus: Any) -> None:
        self._bus = bus

    async def check_authorization(
        self,
        sender: str,
        action_id: str,
        allow_interaction: bool = True,
    ) -> bool:
        """Verify authorization of sender for action_id via PolicyKit1."""
        if not self._enabled:
            return True

        if not self._bus or not _HAS_DBUS:
            logger.debug("No active system bus for polkit check; defaulting to denied")
            return False

        try:
            subject = ("system-bus-name", {"name": Variant("s", sender)})
            details: dict[str, str] = {}
            flags = 1 if allow_interaction else 0
            cancellation_id = ""

            msg = Message(
                destination="org.freedesktop.PolicyKit1",
                path="/org/freedesktop/PolicyKit1/Authority",
                interface="org.freedesktop.PolicyKit1.Authority",
                member="CheckAuthorization",
                signature="(sa{sv})sa{ss}us",
                body=[subject, action_id, details, flags, cancellation_id],
            )
            reply = await self._bus.call(msg)
            if reply.message_type == MessageType.ERROR:
                logger.warning("Polkit CheckAuthorization returned error: %s", reply.body)
                return False
            # Return tuple is (is_authorized, is_challenge, details)
            is_authorized = reply.body[0]
            return bool(is_authorized)
        except Exception as e:
            logger.error("Polkit CheckAuthorization call failed: %s", e)
            return False


class SCTRLDBusInterface(ServiceInterface):
    """D-Bus interface export for io.github.sctrl.sctrl.Control."""

    def __init__(
        self,
        service: SCTRLService,
        authorizer: PolkitAuthorizer | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(DBUS_INTERFACE)
        self._service = service
        self._authorizer = authorizer if authorizer is not None else PolkitAuthorizer()
        self._rate_limiter = rate_limiter if rate_limiter is not None else RateLimiter()

        # Subscribe to service events
        self._service.subscribe_telemetry(self._on_telemetry)
        self._service.subscribe_alert(self._on_alert)

    def _get_sender(self) -> str:
        return current_sender_var.get()

    async def _verify_caller(self, sender: str, action_id: str) -> None:
        """Enforce rate limiting and polkit authorization."""
        self._rate_limiter.check(sender)
        authorized = await self._authorizer.check_authorization(sender, action_id)
        if not authorized:
            raise PermissionDeniedError(
                f"Caller '{sender}' not authorized for action '{action_id}'",
                code=ErrorCode.AUTHORIZATION_FAILED,
            )

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

    # Read Methods (No polkit write authorization required)
    @method()
    def GetState(self) -> "s":
        """Return overall daemon state as JSON."""
        sender = self._get_sender()
        self._rate_limiter.check(sender)
        return json.dumps(self._service.get_state().to_dict())

    @method()
    def GetTelemetry(self) -> "s":
        """Return latest telemetry snapshot as JSON."""
        sender = self._get_sender()
        self._rate_limiter.check(sender)
        return json.dumps(self._service.get_telemetry().to_dict())

    @method()
    def GetCapabilities(self) -> "s":
        """Return discovered capabilities list as JSON."""
        sender = self._get_sender()
        self._rate_limiter.check(sender)
        return json.dumps(self._service.get_capabilities())

    @method()
    def GetDiagnostics(self) -> "s":
        """Return full diagnostic report as JSON."""
        sender = self._get_sender()
        self._rate_limiter.check(sender)
        return json.dumps(self._service.get_diagnostics().to_dict())

    # Write Methods (Enforced via caller sender + polkit authorization)
    async def set_fan_mode_impl(self, mode: str, sender: str) -> str:
        await self._verify_caller(sender, POLKIT_ACTION_WRITE)
        # Identify lease holder strictly by D-Bus caller sender
        res = self._service.set_fan_mode(mode, holder=sender)
        return json.dumps(res)

    @method()
    async def SetFanMode(self, mode: "s") -> "s":
        """Set fan mode (auto, max)."""
        sender = self._get_sender()
        return await self.set_fan_mode_impl(mode, sender=sender)

    async def set_custom_curve_impl(self, curve_json: str, sender: str) -> str:
        await self._verify_caller(sender, POLKIT_ACTION_WRITE)
        data = json.loads(curve_json)
        cpu_points = [FanCurvePoint(p["temp_c"], p["speed_percent"]) for p in data.get("cpu_points", [])]
        gpu_points = [FanCurvePoint(p["temp_c"], p["speed_percent"]) for p in data.get("gpu_points", [])]
        cpu_curve = FanCurve(points=cpu_points) if cpu_points else None
        gpu_curve = FanCurve(points=gpu_points) if gpu_points else None

        res = self._service.set_custom_curve(sender, cpu_curve, gpu_curve)
        return json.dumps(res)

    @method()
    async def SetCustomCurve(self, curve_json: "s") -> "s":
        """Apply custom fan curve JSON."""
        sender = self._get_sender()
        return await self.set_custom_curve_impl(curve_json, sender=sender)

    async def renew_fan_lease_impl(self, duration_s: int, sender: str) -> bool:
        await self._verify_caller(sender, POLKIT_ACTION_WRITE)
        return self._service.renew_fan_lease(sender, duration_s)

    @method()
    async def RenewFanLease(self, duration_s: "i") -> "b":
        """Renew active fan control lease."""
        sender = self._get_sender()
        return await self.renew_fan_lease_impl(duration_s, sender=sender)

    async def set_profile_impl(self, profile: str, sender: str) -> str:
        await self._verify_caller(sender, POLKIT_ACTION_WRITE)
        res = self._service.set_profile(profile)
        return json.dumps(res)

    @method()
    async def SetProfile(self, profile: "s") -> "s":
        """Set performance profile."""
        sender = self._get_sender()
        return await self.set_profile_impl(profile, sender=sender)

    async def set_charge_limit_impl(self, percent: int, sender: str) -> str:
        await self._verify_caller(sender, POLKIT_ACTION_WRITE)
        res = self._service.set_charge_limit(percent)
        return json.dumps(res)

    @method()
    async def SetChargeLimit(self, percent: "i") -> "s":
        """Set battery charge limit percentage."""
        sender = self._get_sender()
        return await self.set_charge_limit_impl(percent, sender=sender)

    async def set_keyboard_brightness_impl(self, level: int, sender: str) -> str:
        await self._verify_caller(sender, POLKIT_ACTION_WRITE)
        res = self._service.set_keyboard_brightness(level)
        return json.dumps(res)

    @method()
    async def SetKeyboardBrightness(self, level: "i") -> "s":
        """Set keyboard brightness level (0-100)."""
        sender = self._get_sender()
        return await self.set_keyboard_brightness_impl(level, sender=sender)

    async def set_keyboard_zone_color_impl(self, zone_id: int, r: int, g: int, b: int, sender: str) -> str:
        await self._verify_caller(sender, POLKIT_ACTION_WRITE)
        res = self._service.set_keyboard_zone_color(zone_id, r, g, b)
        return json.dumps(res)

    @method()
    async def SetKeyboardZoneColor(self, zone_id: "i", r: "i", g: "i", b: "i") -> "s":
        """Set keyboard RGB zone color."""
        sender = self._get_sender()
        return await self.set_keyboard_zone_color_impl(zone_id, r, g, b, sender=sender)

    async def set_keyboard_effect_impl(self, effect: str, speed: int, sender: str) -> str:
        await self._verify_caller(sender, POLKIT_ACTION_WRITE)
        res = self._service.set_keyboard_effect(effect, speed)
        return json.dumps(res)

    @method()
    async def SetKeyboardEffect(self, effect: "s", speed: "i") -> "s":
        """Set keyboard animation effect and speed."""
        sender = self._get_sender()
        return await self.set_keyboard_effect_impl(effect, speed, sender=sender)

    # Opt-in: Stronger Polkit action (POLKIT_ACTION_ADMIN)
    async def set_feature_optin_impl(self, feature_id: str, opted_in: bool, sender: str) -> bool:
        await self._verify_caller(sender, POLKIT_ACTION_ADMIN)
        self._service.set_feature_optin(feature_id, opted_in)
        return True

    @method()
    async def SetFeatureOptIn(self, feature_id: "s", opted_in: "b") -> "b":
        """Set opt-in for detected tier writes."""
        sender = self._get_sender()
        return await self.set_feature_optin_impl(feature_id, opted_in, sender=sender)


class DBusServer:
    """Manages D-Bus connection and lifecycle."""

    def __init__(self, service: SCTRLService, use_session_bus: bool = False) -> None:
        self._service = service
        self._use_session_bus = use_session_bus
        self._bus: MessageBus | None = None
        self._interface: SCTRLDBusInterface | None = None
        self._authorizer = PolkitAuthorizer()

    async def start(self) -> None:
        if not _HAS_DBUS:
            logger.warning("dbus-next is not installed; D-Bus server disabled")
            return

        try:
            from dbus_next.aio import MessageBus
            from dbus_next.constants import BusType

            bus_type = BusType.SESSION if self._use_session_bus else BusType.SYSTEM
            self._bus = await MessageBus(bus_type=bus_type).connect()
            self._authorizer.set_bus(self._bus)

            # Hook message handler to record caller D-Bus sender into contextvar
            orig_make_method_handler = self._bus._make_method_handler

            def hooked_make_method_handler(interface: Any, method_def: Any) -> Any:
                handler = orig_make_method_handler(interface, method_def)

                def wrapped_handler(msg: Any, send_reply: Any) -> Any:
                    current_sender_var.set(msg.sender or "unknown")
                    return handler(msg, send_reply)

                return wrapped_handler

            self._bus._make_method_handler = hooked_make_method_handler

            self._interface = SCTRLDBusInterface(self._service, authorizer=self._authorizer)
            self._bus.export(DBUS_OBJECT_PATH, self._interface)

            reply = await self._bus.request_name(DBUS_SERVICE_NAME)
            logger.info("D-Bus service %s exported on %s (result: %s)", DBUS_SERVICE_NAME, bus_type.name, reply)
        except Exception as e:
            logger.warning("Failed to connect or export on D-Bus: %s", e)

    async def stop(self) -> None:
        if self._bus:
            self._bus.disconnect()
            logger.info("Disconnected from D-Bus")

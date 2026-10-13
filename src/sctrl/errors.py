"""Structured error types for SCTRL.

Every error carries enough context for structured logging and for the GUI
to present a useful, non-technical explanation to the user.
"""

from __future__ import annotations

from enum import Enum, unique
from typing import Any


@unique
class ErrorCode(Enum):
    """Machine-readable error codes returned over D-Bus and used in logs."""

    # General
    UNKNOWN = "unknown"
    INTERNAL = "internal_error"
    INVALID_ARGUMENT = "invalid_argument"
    NOT_IMPLEMENTED = "not_implemented"

    # Hardware
    DEVICE_NOT_FOUND = "device_not_found"
    DEVICE_DISAPPEARED = "device_disappeared"
    DRIVER_MISSING = "driver_missing"
    DRIVER_INCOMPATIBLE = "driver_incompatible"
    PERMISSION_DENIED = "permission_denied"
    READ_FAILED = "read_failed"
    WRITE_FAILED = "write_failed"
    WRITE_REJECTED = "write_rejected"
    VALUE_OUT_OF_RANGE = "value_out_of_range"
    VERIFICATION_FAILED = "verification_failed"
    INTERFACE_BUSY = "interface_busy"

    # Capability / tier
    FEATURE_UNAVAILABLE = "feature_unavailable"
    FEATURE_UNSUPPORTED = "feature_unsupported"
    BLOCKED_BY_TIER = "blocked_by_tier"
    OPTIN_REQUIRED = "optin_required"

    # Configuration
    CONFIG_INVALID = "config_invalid"
    CONFIG_SCHEMA_MISMATCH = "config_schema_mismatch"
    CONFIG_WRITE_FAILED = "config_write_failed"
    PROFILE_NOT_FOUND = "profile_not_found"
    PROFILE_MALFORMED = "profile_malformed"

    # Daemon / D-Bus
    DAEMON_NOT_RUNNING = "daemon_not_running"
    DBUS_DISCONNECTED = "dbus_disconnected"
    RATE_LIMITED = "rate_limited"
    AUTHORIZATION_FAILED = "authorization_failed"

    # Fan control
    LEASE_EXPIRED = "lease_expired"
    LEASE_NOT_HELD = "lease_not_held"
    FAN_CURVE_INVALID = "fan_curve_invalid"
    EMERGENCY_OVERRIDE_ACTIVE = "emergency_override_active"

    # Thermal
    SENSOR_STALE = "sensor_stale"
    THERMAL_CRITICAL = "thermal_critical"


class SCTRLError(Exception):
    """Base exception for all SCTRL errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.UNKNOWN,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize for D-Bus or logging."""
        return {
            "code": self.code.value,
            "message": str(self),
            "details": self.details,
        }


class HardwareError(SCTRLError):
    """Error originating from hardware interaction."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.READ_FAILED,
        device: str = "",
        interface: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details = {"device": device, "interface": interface}
        if details:
            full_details.update(details)
        super().__init__(message, code, full_details)
        self.device = device
        self.interface = interface


class TierBlockedError(SCTRLError):
    """Feature blocked by the current support tier."""

    def __init__(
        self,
        feature: str,
        tier: str,
        reason: str,
    ) -> None:
        super().__init__(
            f"Feature '{feature}' blocked on tier '{tier}': {reason}",
            ErrorCode.BLOCKED_BY_TIER,
            {"feature": feature, "tier": tier, "reason": reason},
        )


class ValidationError(SCTRLError):
    """Input validation failure."""

    def __init__(
        self,
        message: str,
        field: str = "",
        value: Any = None,
        valid_range: tuple[Any, Any] | None = None,
    ) -> None:
        details: dict[str, Any] = {"field": field}
        if value is not None:
            details["value"] = value
        if valid_range is not None:
            details["valid_range"] = list(valid_range)
        super().__init__(message, ErrorCode.INVALID_ARGUMENT, details)


class ConfigError(SCTRLError):
    """Configuration loading or validation failure."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.CONFIG_INVALID,
        path: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details: dict[str, Any] = {"path": path}
        if details:
            full_details.update(details)
        super().__init__(message, code, full_details)


class LeaseError(SCTRLError):
    """Fan-control lease error."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.LEASE_EXPIRED,
    ) -> None:
        super().__init__(message, code)


class UnsupportedError(SCTRLError):
    """Operation or feature unsupported on this platform."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.FEATURE_UNSUPPORTED,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code, details)


class HardwareWriteError(HardwareError):
    """Failed write to hardware."""

    def __init__(
        self,
        message: str,
        feature: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        full_details = {"feature": feature}
        if details:
            full_details.update(details)
        super().__init__(message, ErrorCode.WRITE_FAILED, interface=feature, details=full_details)

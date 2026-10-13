"""Core data models for SCTRL.

All data structures used across daemon, GUI, and tests. Uses dataclasses
for clarity and type safety. All temperatures in degrees Celsius,
power in watts, speeds in driver-native units (typically RPM or percent).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, unique
from typing import Any


# ---------------------------------------------------------------------------
# Capability and feature status
# ---------------------------------------------------------------------------

@unique
class FeatureStatus(Enum):
    """Runtime status of a hardware feature."""
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    PERMISSION_DENIED = "permission_denied"
    DRIVER_MISSING = "driver_missing"
    DETECTED_UNVERIFIED = "detected_unverified"
    TEMPORARILY_FAILED = "temporarily_failed"


@unique
class SupportTier(Enum):
    """Model support tier, computed at runtime."""
    VERIFIED = "verified"
    COMMUNITY = "community"
    DETECTED = "detected"
    UNSUPPORTED = "unsupported"


@unique
class FeatureId(Enum):
    """Canonical feature identifiers."""
    CPU_TEMP = "cpu_temp"
    GPU_TEMP = "gpu_temp"
    CPU_UTIL = "cpu_util"
    GPU_UTIL = "gpu_util"
    CPU_FAN_RPM = "cpu_fan_rpm"
    GPU_FAN_RPM = "gpu_fan_rpm"
    CPU_POWER = "cpu_power"
    GPU_POWER = "gpu_power"
    RAM_UTIL = "ram_util"
    BATTERY_CHARGE = "battery_charge"
    BATTERY_STATE = "battery_state"
    CHARGE_LIMIT = "charge_limit"
    FAN_MODE = "fan_mode"
    FAN_CURVE = "fan_curve"
    PERFORMANCE_PROFILE = "performance_profile"
    KEYBOARD_BRIGHTNESS = "keyboard_brightness"
    KEYBOARD_RGB = "keyboard_rgb"
    KEYBOARD_EFFECT = "keyboard_effect"
    PLATFORM_PROFILE = "platform_profile"
    UPTIME = "uptime"


@dataclass(frozen=True)
class CapabilityRecord:
    """Runtime record for a single discovered feature."""
    feature_id: FeatureId
    status: FeatureStatus
    interface: str = ""
    readable: bool = False
    writable: bool = False
    current_value: Any = None
    supported_range: tuple[Any, Any] | None = None
    supported_values: list[str] | None = None
    last_probe_time: float = 0.0
    last_error: str = ""
    confidence: str = "runtime"
    tier: SupportTier = SupportTier.UNSUPPORTED

    def to_dict(self) -> dict[str, Any]:
        """Serialize for D-Bus transport."""
        return {
            "feature_id": self.feature_id.value,
            "status": self.status.value,
            "interface": self.interface,
            "readable": self.readable,
            "writable": self.writable,
            "current_value": self.current_value,
            "supported_range": list(self.supported_range) if self.supported_range else None,
            "supported_values": self.supported_values,
            "last_probe_time": self.last_probe_time,
            "last_error": self.last_error,
            "confidence": self.confidence,
            "tier": self.tier.value,
        }


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

@unique
class ValueQuality(Enum):
    """Distinguishes measured, estimated, and unavailable values."""
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


@dataclass
class SensorReading:
    """A single sensor reading with metadata."""
    value: float | None
    unit: str
    quality: ValueQuality
    timestamp: float = field(default_factory=time.monotonic)
    source: str = ""

    @property
    def is_available(self) -> bool:
        return self.quality not in (ValueQuality.UNAVAILABLE,) and self.value is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "unit": self.unit,
            "quality": self.quality.value,
            "timestamp": self.timestamp,
            "source": self.source,
        }


@dataclass
class TelemetrySnapshot:
    """Complete telemetry state at a point in time."""
    timestamp: float = field(default_factory=time.time)

    cpu_temp: SensorReading = field(
        default_factory=lambda: SensorReading(None, "C", ValueQuality.UNAVAILABLE)
    )
    gpu_temp: SensorReading = field(
        default_factory=lambda: SensorReading(None, "C", ValueQuality.UNAVAILABLE)
    )
    cpu_util: SensorReading = field(
        default_factory=lambda: SensorReading(None, "%", ValueQuality.UNAVAILABLE)
    )
    gpu_util: SensorReading = field(
        default_factory=lambda: SensorReading(None, "%", ValueQuality.UNAVAILABLE)
    )
    cpu_fan_rpm: SensorReading = field(
        default_factory=lambda: SensorReading(None, "RPM", ValueQuality.UNAVAILABLE)
    )
    gpu_fan_rpm: SensorReading = field(
        default_factory=lambda: SensorReading(None, "RPM", ValueQuality.UNAVAILABLE)
    )
    cpu_power: SensorReading = field(
        default_factory=lambda: SensorReading(None, "W", ValueQuality.UNAVAILABLE)
    )
    gpu_power: SensorReading = field(
        default_factory=lambda: SensorReading(None, "W", ValueQuality.UNAVAILABLE)
    )
    ram_used_bytes: SensorReading = field(
        default_factory=lambda: SensorReading(None, "B", ValueQuality.UNAVAILABLE)
    )
    ram_total_bytes: SensorReading = field(
        default_factory=lambda: SensorReading(None, "B", ValueQuality.UNAVAILABLE)
    )
    ram_util: SensorReading = field(
        default_factory=lambda: SensorReading(None, "%", ValueQuality.UNAVAILABLE)
    )
    battery_percent: SensorReading = field(
        default_factory=lambda: SensorReading(None, "%", ValueQuality.UNAVAILABLE)
    )
    battery_state: str = "unknown"
    charge_limit: SensorReading = field(
        default_factory=lambda: SensorReading(None, "%", ValueQuality.UNAVAILABLE)
    )
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "cpu_temp": self.cpu_temp.to_dict(),
            "gpu_temp": self.gpu_temp.to_dict(),
            "cpu_util": self.cpu_util.to_dict(),
            "gpu_util": self.gpu_util.to_dict(),
            "cpu_fan_rpm": self.cpu_fan_rpm.to_dict(),
            "gpu_fan_rpm": self.gpu_fan_rpm.to_dict(),
            "cpu_power": self.cpu_power.to_dict(),
            "gpu_power": self.gpu_power.to_dict(),
            "ram_used_bytes": self.ram_used_bytes.to_dict(),
            "ram_total_bytes": self.ram_total_bytes.to_dict(),
            "ram_util": self.ram_util.to_dict(),
            "battery_percent": self.battery_percent.to_dict(),
            "battery_state": self.battery_state,
            "charge_limit": self.charge_limit.to_dict(),
            "uptime_seconds": self.uptime_seconds,
        }


# ---------------------------------------------------------------------------
# Fan control
# ---------------------------------------------------------------------------

@unique
class FanMode(Enum):
    """Logical fan modes."""
    AUTO = "auto"
    MAX = "max"
    CUSTOM = "custom"


@dataclass(frozen=True)
class FanCurvePoint:
    """One point on a temperature-to-speed fan curve."""
    temp_c: int
    speed_percent: int

    def to_dict(self) -> dict[str, int]:
        return {"temp_c": self.temp_c, "speed_percent": self.speed_percent}


@dataclass
class FanCurve:
    """A complete fan curve definition."""
    points: list[FanCurvePoint]
    hysteresis_c: int = 3
    min_dwell_s: int = 5
    below_first_speed: int = 0
    above_last_speed: int = 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": [p.to_dict() for p in self.points],
            "hysteresis_c": self.hysteresis_c,
            "min_dwell_s": self.min_dwell_s,
            "below_first_speed": self.below_first_speed,
            "above_last_speed": self.above_last_speed,
        }


@dataclass
class FanLease:
    """A fan-control session lease."""
    holder: str
    fan_target: str  # "cpu", "gpu", "both"
    mode: FanMode
    granted_at: float = field(default_factory=time.monotonic)
    expires_at: float = 0.0
    curve: FanCurve | None = None

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at

    def renew(self, duration_s: int) -> None:
        self.expires_at = time.monotonic() + duration_s


# ---------------------------------------------------------------------------
# Performance profiles
# ---------------------------------------------------------------------------

@unique
class LogicalProfile(Enum):
    """Logical performance profiles."""
    QUIET = "quiet"
    BALANCED = "balanced"
    PERFORMANCE = "performance"
    TURBO = "turbo"


@dataclass
class ProfileState:
    """Current performance profile state."""
    requested: LogicalProfile | None = None
    applied: LogicalProfile | None = None
    firmware_reported: str = ""
    available_profiles: list[LogicalProfile] = field(default_factory=list)
    unavailable_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested.value if self.requested else None,
            "applied": self.applied.value if self.applied else None,
            "firmware_reported": self.firmware_reported,
            "available_profiles": [p.value for p in self.available_profiles],
            "unavailable_reason": self.unavailable_reason,
        }


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

@dataclass
class RGBColor:
    """RGB color value."""
    r: int = 0
    g: int = 0
    b: int = 0

    def __post_init__(self) -> None:
        for c, name in [(self.r, "r"), (self.g, "g"), (self.b, "b")]:
            if not 0 <= c <= 255:
                raise ValueError(f"RGB component {name}={c} out of range [0, 255]")

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def to_dict(self) -> dict[str, int]:
        return {"r": self.r, "g": self.g, "b": self.b}


@unique
class KeyboardEffect(Enum):
    """Supported keyboard lighting effects."""
    STATIC = "static"
    BREATHING = "breathing"
    OFF = "off"


@dataclass
class KeyboardZone:
    """A single keyboard lighting zone."""
    zone_id: int
    color: RGBColor = field(default_factory=RGBColor)
    effect: KeyboardEffect = KeyboardEffect.STATIC
    speed: int = 50  # 0-100
    brightness: int = 100  # 0-100

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "color": self.color.to_dict(),
            "effect": self.effect.value,
            "speed": self.speed,
            "brightness": self.brightness,
        }


# ---------------------------------------------------------------------------
# DMI / system info
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DMIInfo:
    """System DMI identification, read-only."""
    product_name: str = ""
    board_name: str = ""
    vendor: str = ""
    bios_version: str = ""
    bios_date: str = ""
    sys_vendor: str = ""
    chassis_type: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "product_name": self.product_name,
            "board_name": self.board_name,
            "vendor": self.vendor,
            "bios_version": self.bios_version,
            "bios_date": self.bios_date,
            "sys_vendor": self.sys_vendor,
            "chassis_type": self.chassis_type,
        }


# ---------------------------------------------------------------------------
# Daemon state
# ---------------------------------------------------------------------------

@dataclass
class DaemonState:
    """Overall daemon state exposed over D-Bus."""
    tier: SupportTier = SupportTier.UNSUPPORTED
    tier_reason: str = ""
    model_profile: str = ""
    dmi: DMIInfo = field(default_factory=DMIInfo)
    fan_mode: FanMode = FanMode.AUTO
    fan_lease_active: bool = False
    fan_lease_remaining_s: int = 0
    profile: ProfileState = field(default_factory=ProfileState)
    emergency_override: bool = False
    mock_mode: bool = False
    api_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "tier_reason": self.tier_reason,
            "model_profile": self.model_profile,
            "dmi": self.dmi.to_dict(),
            "fan_mode": self.fan_mode.value,
            "fan_lease_active": self.fan_lease_active,
            "fan_lease_remaining_s": self.fan_lease_remaining_s,
            "profile": self.profile.to_dict(),
            "emergency_override": self.emergency_override,
            "mock_mode": self.mock_mode,
            "api_version": self.api_version,
        }


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@dataclass
class DiagnosticReport:
    """Structured diagnostic report."""
    timestamp: float = field(default_factory=time.time)
    dmi: DMIInfo = field(default_factory=DMIInfo)
    tier: SupportTier = SupportTier.UNSUPPORTED
    tier_reason: str = ""
    model_profile: str = ""
    kernel_version: str = ""
    distro: str = ""
    active_drivers: list[str] = field(default_factory=list)
    capabilities: list[dict[str, Any]] = field(default_factory=list)
    sensor_failures: list[str] = field(default_factory=list)
    recent_errors: list[str] = field(default_factory=list)
    daemon_version: str = ""
    mock_mode: bool = False
    optin_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "dmi": self.dmi.to_dict(),
            "tier": self.tier.value,
            "tier_reason": self.tier_reason,
            "model_profile": self.model_profile,
            "kernel_version": self.kernel_version,
            "distro": self.distro,
            "active_drivers": self.active_drivers,
            "capabilities": self.capabilities,
            "sensor_failures": self.sensor_failures,
            "recent_errors": self.recent_errors,
            "daemon_version": self.daemon_version,
            "mock_mode": self.mock_mode,
            "optin_features": self.optin_features,
        }

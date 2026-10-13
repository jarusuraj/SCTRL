"""Hardware abstraction base interfaces for SCTRL.

Defines abstract base classes for every category of hardware interaction.
Concrete implementations (real sysfs, nvidia-smi, mock) implement these
interfaces. The daemon selects the appropriate backend at startup.

All temperatures: degrees Celsius (float).
All power: watts (float).
All fan speeds: driver-native units (typically RPM or percent as int).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sctrl.models import (
    CapabilityRecord,
    DMIInfo,
    FanCurve,
    FanMode,
    FeatureId,
    FeatureStatus,
    KeyboardEffect,
    LogicalProfile,
    RGBColor,
    SensorReading,
    SupportTier,
    ValueQuality,
)


# ---------------------------------------------------------------------------
# Write result tracking
# ---------------------------------------------------------------------------

@dataclass
class WriteResult:
    """Result of a hardware write operation."""
    success: bool
    feature: FeatureId
    requested_value: Any
    actual_value: Any = None
    verified: bool = False
    backend: str = ""
    error: str = ""
    timestamp: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "feature": self.feature.value,
            "requested_value": self.requested_value,
            "actual_value": self.actual_value,
            "verified": self.verified,
            "backend": self.backend,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Sensor backend
# ---------------------------------------------------------------------------

class SensorBackend(ABC):
    """Abstract interface for reading sensor data."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Unique identifier for this backend."""
        ...

    @abstractmethod
    def probe(self) -> list[CapabilityRecord]:
        """Discover available sensors and return capability records."""
        ...

    @abstractmethod
    def read_cpu_temp(self) -> SensorReading:
        """Read CPU temperature in degrees Celsius."""
        ...

    @abstractmethod
    def read_gpu_temp(self) -> SensorReading:
        """Read GPU temperature in degrees Celsius."""
        ...

    @abstractmethod
    def read_cpu_fan_rpm(self) -> SensorReading:
        """Read CPU fan speed in RPM."""
        ...

    @abstractmethod
    def read_gpu_fan_rpm(self) -> SensorReading:
        """Read GPU fan speed in RPM."""
        ...

    @abstractmethod
    def read_cpu_power(self) -> SensorReading:
        """Read CPU package power in watts."""
        ...

    @abstractmethod
    def read_gpu_power(self) -> SensorReading:
        """Read GPU power in watts."""
        ...

    def cleanup(self) -> None:
        """Release resources held by this backend."""


# ---------------------------------------------------------------------------
# Fan control backend
# ---------------------------------------------------------------------------

class FanControlBackend(ABC):
    """Abstract interface for fan control."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        ...

    @abstractmethod
    def probe(self) -> list[CapabilityRecord]:
        """Discover fan control capabilities."""
        ...

    @abstractmethod
    def get_current_mode(self) -> FanMode:
        """Get current fan control mode."""
        ...

    @abstractmethod
    def set_mode_auto(self) -> WriteResult:
        """Return fans to firmware automatic control."""
        ...

    @abstractmethod
    def set_mode_max(self) -> WriteResult:
        """Set fans to maximum speed."""
        ...

    @abstractmethod
    def set_fan_speed(self, fan: str, speed_percent: int) -> WriteResult:
        """Set a specific fan speed (percent of driver range).

        Args:
            fan: Fan identifier ("cpu" or "gpu").
            speed_percent: Requested speed percentage.
        """
        ...

    @abstractmethod
    def get_supported_range(self, fan: str) -> tuple[int, int]:
        """Get the supported speed range for a fan (min_pct, max_pct)."""
        ...

    def cleanup(self) -> None:
        """Release fan control resources."""


# ---------------------------------------------------------------------------
# Performance profile backend
# ---------------------------------------------------------------------------

class ProfileBackend(ABC):
    """Abstract interface for performance profile control."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        ...

    @abstractmethod
    def probe(self) -> list[CapabilityRecord]:
        """Discover available profiles."""
        ...

    @abstractmethod
    def get_current_profile(self) -> str:
        """Get the current firmware-reported profile string."""
        ...

    @abstractmethod
    def get_available_profiles(self) -> list[str]:
        """List all available profile strings from the interface."""
        ...

    @abstractmethod
    def set_profile(self, profile_value: str) -> WriteResult:
        """Set a profile using the driver-specific value string."""
        ...

    def cleanup(self) -> None:
        """Release resources."""


# ---------------------------------------------------------------------------
# Battery backend
# ---------------------------------------------------------------------------

class BatteryBackend(ABC):
    """Abstract interface for battery monitoring and charge control."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        ...

    @abstractmethod
    def probe(self) -> list[CapabilityRecord]:
        """Discover battery capabilities."""
        ...

    @abstractmethod
    def read_charge_percent(self) -> SensorReading:
        """Read current battery charge percentage."""
        ...

    @abstractmethod
    def read_charge_state(self) -> str:
        """Read charging state (charging, discharging, full, not-charging, unknown)."""
        ...

    @abstractmethod
    def get_charge_limit(self) -> int | None:
        """Get current charge limit, or None if unsupported."""
        ...

    @abstractmethod
    def set_charge_limit(self, percent: int) -> WriteResult:
        """Set charge limit percentage."""
        ...

    @abstractmethod
    def get_charge_limit_range(self) -> tuple[int, int] | None:
        """Get supported charge limit range, or None if unsupported."""
        ...

    def cleanup(self) -> None:
        """Release resources."""


# ---------------------------------------------------------------------------
# Keyboard backend
# ---------------------------------------------------------------------------

class KeyboardBackend(ABC):
    """Abstract interface for keyboard backlight and RGB control."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        ...

    @abstractmethod
    def probe(self) -> list[CapabilityRecord]:
        """Discover keyboard lighting capabilities."""
        ...

    @abstractmethod
    def get_brightness(self) -> int:
        """Get current backlight brightness (0-100)."""
        ...

    @abstractmethod
    def set_brightness(self, level: int) -> WriteResult:
        """Set backlight brightness (0-100)."""
        ...

    @abstractmethod
    def get_zone_count(self) -> int:
        """Get number of independently controllable zones."""
        ...

    @abstractmethod
    def get_zone_color(self, zone_id: int) -> RGBColor | None:
        """Get current color of a zone."""
        ...

    @abstractmethod
    def set_zone_color(self, zone_id: int, color: RGBColor) -> WriteResult:
        """Set color for a specific zone."""
        ...

    @abstractmethod
    def set_effect(self, effect: KeyboardEffect, speed: int = 50) -> WriteResult:
        """Set keyboard lighting effect."""
        ...

    @abstractmethod
    def get_supported_effects(self) -> list[KeyboardEffect]:
        """List supported effects."""
        ...

    def cleanup(self) -> None:
        """Release resources."""


# ---------------------------------------------------------------------------
# System info backend
# ---------------------------------------------------------------------------

class SystemInfoBackend(ABC):
    """Abstract interface for system information retrieval."""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        ...

    @abstractmethod
    def read_dmi(self) -> DMIInfo:
        """Read DMI identification data."""
        ...

    @abstractmethod
    def read_cpu_util(self) -> SensorReading:
        """Read CPU utilization percentage."""
        ...

    @abstractmethod
    def read_ram_usage(self) -> tuple[SensorReading, SensorReading, SensorReading]:
        """Read RAM usage: (used_bytes, total_bytes, util_percent)."""
        ...

    @abstractmethod
    def read_gpu_util(self) -> SensorReading:
        """Read GPU utilization percentage."""
        ...

    @abstractmethod
    def read_uptime(self) -> float:
        """Read system uptime in seconds."""
        ...

    @abstractmethod
    def is_gpu_suspended(self) -> bool:
        """Check if the discrete GPU is runtime-suspended."""
        ...

    @abstractmethod
    def get_kernel_version(self) -> str:
        """Get the running kernel version string."""
        ...

    @abstractmethod
    def get_distro_info(self) -> str:
        """Get distribution name and version."""
        ...

    def cleanup(self) -> None:
        """Release resources."""

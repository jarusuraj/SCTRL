"""Mock hardware backend for SCTRL.

Provides complete simulation of all hardware interfaces for testing
and GUI development. Never writes to real hardware or system files.

Supports simulating every support tier and multiple failure conditions:
- Normal operation for verified, community, detected, unsupported tiers
- Permission failures
- Missing drivers
- Device disappearance
- Stale sensor readings
- Failed and rejected writes
- Thermal warning transitions
- Fan lease expiry
- BIOS version mismatch downgrade
"""

from __future__ import annotations

import math
import random
import tempfile
import time
from dataclasses import dataclass, field
from enum import Enum, unique
from pathlib import Path
from typing import Any

from sctrl.models import (
    CapabilityRecord,
    DMIInfo,
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

from daemon.hardware.base import (
    BatteryBackend,
    FanControlBackend,
    KeyboardBackend,
    ProfileBackend,
    SensorBackend,
    SystemInfoBackend,
    WriteResult,
)


# ---------------------------------------------------------------------------
# Mock model configurations
# ---------------------------------------------------------------------------

@unique
class MockModel(Enum):
    """Pre-configured mock models for each support tier."""
    VERIFIED = "verified"
    COMMUNITY = "community"
    BIOS_MISMATCH = "bios_mismatch"
    DETECTED = "detected"
    UNSUPPORTED = "unsupported"


@dataclass
class MockConfig:
    """Configuration for mock backend behavior."""
    model: MockModel = MockModel.VERIFIED
    seed: int | None = None
    simulate_failures: bool = False
    simulate_stale_sensors: bool = False
    simulate_device_disappearance: bool = False
    simulate_permission_denied: bool = False
    simulate_driver_missing: bool = False
    gpu_suspended: bool = False
    deterministic: bool = True

    # Simulated values
    base_cpu_temp: float = 55.0
    base_gpu_temp: float = 50.0
    base_cpu_fan_rpm: int = 2200
    base_gpu_fan_rpm: int = 2000
    base_cpu_power: float = 35.0
    base_gpu_power: float = 45.0
    battery_percent: float = 72.0
    battery_state: str = "discharging"
    charge_limit: int = 80
    charge_limit_range: tuple[int, int] = (50, 100)
    ram_used_gb: float = 8.5
    ram_total_gb: float = 16.0


_MOCK_DMI: dict[MockModel, DMIInfo] = {
    MockModel.VERIFIED: DMIInfo(
        product_name="PHN16-72",
        board_name="Covini_PH16-72",
        vendor="Acer",
        bios_version="V1.06",
        bios_date="06/15/2024",
        sys_vendor="Acer",
        chassis_type="10",
    ),
    MockModel.COMMUNITY: DMIInfo(
        product_name="PHN16-72",
        board_name="Covini_PH16-72",
        vendor="Acer",
        bios_version="V1.06",
        bios_date="06/15/2024",
        sys_vendor="Acer",
        chassis_type="10",
    ),
    MockModel.BIOS_MISMATCH: DMIInfo(
        product_name="PHN16-72",
        board_name="Covini_PH16-72",
        vendor="Acer",
        bios_version="V2.01",
        bios_date="01/10/2025",
        sys_vendor="Acer",
        chassis_type="10",
    ),
    MockModel.DETECTED: DMIInfo(
        product_name="AN515-58",
        board_name="Onda_AN515-58",
        vendor="Acer",
        bios_version="V1.14",
        bios_date="03/20/2024",
        sys_vendor="Acer",
        chassis_type="10",
    ),
    MockModel.UNSUPPORTED: DMIInfo(
        product_name="ThinkPad T14s Gen 4",
        board_name="21F6CTO1WW",
        vendor="LENOVO",
        bios_version="N3MET39W (1.19)",
        bios_date="09/08/2024",
        sys_vendor="LENOVO",
        chassis_type="10",
    ),
}


# ---------------------------------------------------------------------------
# Sensor simulation
# ---------------------------------------------------------------------------

class _SensorSimulator:
    """Generates realistic-looking sensor values with smooth variation."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._rng = random.Random(config.seed if config.seed is not None else 42)
        self._start_time = time.monotonic()
        self._phase = self._rng.uniform(0, 2 * math.pi)

    def _elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def _wave(self, amplitude: float, period_s: float) -> float:
        if self._config.deterministic:
            return amplitude * math.sin(self._elapsed() / period_s * 2 * math.pi + self._phase)
        return self._rng.uniform(-amplitude, amplitude)

    def cpu_temp(self) -> float:
        return self._config.base_cpu_temp + self._wave(8.0, 60.0)

    def gpu_temp(self) -> float:
        return self._config.base_gpu_temp + self._wave(6.0, 45.0)

    def cpu_fan_rpm(self) -> int:
        return max(0, int(self._config.base_cpu_fan_rpm + self._wave(300, 30.0)))

    def gpu_fan_rpm(self) -> int:
        return max(0, int(self._config.base_gpu_fan_rpm + self._wave(250, 35.0)))

    def cpu_power(self) -> float:
        return max(0.0, self._config.base_cpu_power + self._wave(10.0, 20.0))

    def gpu_power(self) -> float:
        return max(0.0, self._config.base_gpu_power + self._wave(15.0, 25.0))

    def cpu_util(self) -> float:
        return max(0.0, min(100.0, 35.0 + self._wave(20.0, 15.0)))

    def gpu_util(self) -> float:
        return max(0.0, min(100.0, 25.0 + self._wave(30.0, 20.0)))


# ---------------------------------------------------------------------------
# Mock sensor backend
# ---------------------------------------------------------------------------

class MockSensorBackend(SensorBackend):
    """Mock sensor backend with configurable behavior."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._sim = _SensorSimulator(config)
        self._device_available = True

    @property
    def backend_name(self) -> str:
        return "mock-sensor"

    def set_device_available(self, available: bool) -> None:
        self._device_available = available

    def probe(self) -> list[CapabilityRecord]:
        now = time.monotonic()
        caps: list[CapabilityRecord] = []

        if self._config.simulate_driver_missing:
            for fid in (
                FeatureId.CPU_TEMP, FeatureId.GPU_TEMP,
                FeatureId.CPU_FAN_RPM, FeatureId.GPU_FAN_RPM,
                FeatureId.CPU_POWER, FeatureId.GPU_POWER,
            ):
                caps.append(CapabilityRecord(
                    feature_id=fid,
                    status=FeatureStatus.DRIVER_MISSING,
                    interface=self.backend_name,
                    last_probe_time=now,
                    last_error="Mock: driver not loaded",
                ))
            return caps

        # Temperature sensors
        for fid in (FeatureId.CPU_TEMP, FeatureId.GPU_TEMP):
            status = FeatureStatus.SUPPORTED
            if self._config.simulate_permission_denied:
                status = FeatureStatus.PERMISSION_DENIED
            elif not self._device_available:
                status = FeatureStatus.TEMPORARILY_FAILED

            caps.append(CapabilityRecord(
                feature_id=fid,
                status=status,
                interface=self.backend_name,
                readable=status == FeatureStatus.SUPPORTED,
                writable=False,
                supported_range=(0, 120),
                last_probe_time=now,
                confidence="mock",
            ))

        # Fan RPM sensors
        for fid in (FeatureId.CPU_FAN_RPM, FeatureId.GPU_FAN_RPM):
            caps.append(CapabilityRecord(
                feature_id=fid,
                status=FeatureStatus.SUPPORTED if self._device_available else FeatureStatus.TEMPORARILY_FAILED,
                interface=self.backend_name,
                readable=self._device_available,
                writable=False,
                supported_range=(0, 6000),
                last_probe_time=now,
                confidence="mock",
            ))

        # Power sensors
        for fid in (FeatureId.CPU_POWER, FeatureId.GPU_POWER):
            caps.append(CapabilityRecord(
                feature_id=fid,
                status=FeatureStatus.SUPPORTED if self._device_available else FeatureStatus.TEMPORARILY_FAILED,
                interface=self.backend_name,
                readable=self._device_available,
                writable=False,
                supported_range=(0, 200),
                last_probe_time=now,
                confidence="mock",
            ))

        return caps

    def _make_reading(
        self, value: float, unit: str, unavailable: bool = False
    ) -> SensorReading:
        if unavailable or not self._device_available:
            return SensorReading(None, unit, ValueQuality.UNAVAILABLE, source=self.backend_name)
        if self._config.simulate_stale_sensors:
            return SensorReading(value, unit, ValueQuality.STALE, source=self.backend_name)
        return SensorReading(value, unit, ValueQuality.MEASURED, source=self.backend_name)

    def read_cpu_temp(self) -> SensorReading:
        return self._make_reading(self._sim.cpu_temp(), "C")

    def read_gpu_temp(self) -> SensorReading:
        return self._make_reading(
            self._sim.gpu_temp(), "C",
            unavailable=self._config.gpu_suspended,
        )

    def read_cpu_fan_rpm(self) -> SensorReading:
        return self._make_reading(float(self._sim.cpu_fan_rpm()), "RPM")

    def read_gpu_fan_rpm(self) -> SensorReading:
        return self._make_reading(float(self._sim.gpu_fan_rpm()), "RPM")

    def read_cpu_power(self) -> SensorReading:
        return self._make_reading(self._sim.cpu_power(), "W")

    def read_gpu_power(self) -> SensorReading:
        return self._make_reading(
            self._sim.gpu_power(), "W",
            unavailable=self._config.gpu_suspended,
        )


# ---------------------------------------------------------------------------
# Mock fan control backend
# ---------------------------------------------------------------------------

class MockFanControlBackend(FanControlBackend):
    """Mock fan control with full mode and curve support."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._current_mode = FanMode.AUTO
        self._speeds: dict[str, int] = {"cpu": 50, "gpu": 50}
        self._write_count = 0

    @property
    def backend_name(self) -> str:
        return "mock-fan-control"

    def probe(self) -> list[CapabilityRecord]:
        now = time.monotonic()

        if self._config.model == MockModel.UNSUPPORTED:
            return [
                CapabilityRecord(
                    feature_id=FeatureId.FAN_MODE,
                    status=FeatureStatus.UNSUPPORTED,
                    interface=self.backend_name,
                    last_probe_time=now,
                ),
                CapabilityRecord(
                    feature_id=FeatureId.FAN_CURVE,
                    status=FeatureStatus.UNSUPPORTED,
                    interface=self.backend_name,
                    last_probe_time=now,
                ),
            ]

        if self._config.simulate_driver_missing:
            return [
                CapabilityRecord(
                    feature_id=fid,
                    status=FeatureStatus.DRIVER_MISSING,
                    interface=self.backend_name,
                    last_probe_time=now,
                    last_error="Mock: driver not loaded",
                )
                for fid in (FeatureId.FAN_MODE, FeatureId.FAN_CURVE)
            ]

        writable = self._config.model in (MockModel.VERIFIED, MockModel.COMMUNITY, MockModel.BIOS_MISMATCH)
        status = FeatureStatus.SUPPORTED if writable else FeatureStatus.DETECTED_UNVERIFIED

        return [
            CapabilityRecord(
                feature_id=FeatureId.FAN_MODE,
                status=status,
                interface=self.backend_name,
                readable=True,
                writable=writable,
                current_value=self._current_mode.value,
                supported_values=["auto", "max", "custom"],
                last_probe_time=now,
                confidence="mock",
            ),
            CapabilityRecord(
                feature_id=FeatureId.FAN_CURVE,
                status=status,
                interface=self.backend_name,
                readable=True,
                writable=writable,
                supported_range=(0, 100),
                last_probe_time=now,
                confidence="mock",
            ),
        ]

    def get_current_mode(self) -> FanMode:
        return self._current_mode

    def set_mode_auto(self) -> WriteResult:
        if self._config.simulate_failures and self._write_count % 3 == 2:
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_MODE,
                requested_value="auto",
                backend=self.backend_name,
                error="Mock: simulated write failure",
            )
        self._current_mode = FanMode.AUTO
        self._write_count += 1
        return WriteResult(
            success=True,
            feature=FeatureId.FAN_MODE,
            requested_value="auto",
            actual_value="auto",
            verified=True,
            backend=self.backend_name,
        )

    def set_mode_max(self) -> WriteResult:
        if self._config.simulate_failures and self._write_count % 3 == 2:
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_MODE,
                requested_value="max",
                backend=self.backend_name,
                error="Mock: simulated write failure",
            )
        self._current_mode = FanMode.MAX
        self._write_count += 1
        return WriteResult(
            success=True,
            feature=FeatureId.FAN_MODE,
            requested_value="max",
            actual_value="max",
            verified=True,
            backend=self.backend_name,
        )

    def set_fan_speed(self, fan: str, speed_percent: int) -> WriteResult:
        if fan not in ("cpu", "gpu"):
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_CURVE,
                requested_value=speed_percent,
                backend=self.backend_name,
                error=f"Unknown fan: {fan}",
            )

        min_pct, max_pct = self.get_supported_range(fan)
        if speed_percent < min_pct or speed_percent > max_pct:
            return WriteResult(
                success=False,
                feature=FeatureId.FAN_CURVE,
                requested_value=speed_percent,
                backend=self.backend_name,
                error=f"Speed {speed_percent}% outside range [{min_pct}, {max_pct}]",
            )

        self._speeds[fan] = speed_percent
        self._current_mode = FanMode.CUSTOM
        self._write_count += 1
        return WriteResult(
            success=True,
            feature=FeatureId.FAN_CURVE,
            requested_value=speed_percent,
            actual_value=speed_percent,
            verified=True,
            backend=self.backend_name,
        )

    def get_supported_range(self, fan: str) -> tuple[int, int]:
        return (25, 100)


# ---------------------------------------------------------------------------
# Mock profile backend
# ---------------------------------------------------------------------------

class MockProfileBackend(ProfileBackend):
    """Mock performance profile backend."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._current = "balanced"
        self._available = ["low-power", "balanced", "performance"]
        if config.model in (MockModel.VERIFIED, MockModel.COMMUNITY, MockModel.BIOS_MISMATCH):
            self._available.append("turbo")

    @property
    def backend_name(self) -> str:
        return "mock-platform-profile"

    def probe(self) -> list[CapabilityRecord]:
        now = time.monotonic()

        if self._config.model == MockModel.UNSUPPORTED:
            return [CapabilityRecord(
                feature_id=FeatureId.PERFORMANCE_PROFILE,
                status=FeatureStatus.UNSUPPORTED,
                interface=self.backend_name,
                last_probe_time=now,
            )]

        writable = self._config.model != MockModel.UNSUPPORTED

        return [CapabilityRecord(
            feature_id=FeatureId.PERFORMANCE_PROFILE,
            status=FeatureStatus.SUPPORTED,
            interface=self.backend_name,
            readable=True,
            writable=writable,
            current_value=self._current,
            supported_values=self._available,
            last_probe_time=now,
            confidence="mock",
        )]

    def get_current_profile(self) -> str:
        return self._current

    def get_available_profiles(self) -> list[str]:
        return list(self._available)

    def set_profile(self, profile_value: str) -> WriteResult:
        if profile_value not in self._available:
            return WriteResult(
                success=False,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                backend=self.backend_name,
                error=f"Profile '{profile_value}' not available. Available: {self._available}",
            )

        if self._config.simulate_failures:
            return WriteResult(
                success=False,
                feature=FeatureId.PERFORMANCE_PROFILE,
                requested_value=profile_value,
                backend=self.backend_name,
                error="Mock: simulated write failure",
            )

        self._current = profile_value
        return WriteResult(
            success=True,
            feature=FeatureId.PERFORMANCE_PROFILE,
            requested_value=profile_value,
            actual_value=profile_value,
            verified=True,
            backend=self.backend_name,
        )


# ---------------------------------------------------------------------------
# Mock battery backend
# ---------------------------------------------------------------------------

class MockBatteryBackend(BatteryBackend):
    """Mock battery monitoring and charge control."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._charge_limit: int | None = (
            config.charge_limit
            if config.model != MockModel.UNSUPPORTED
            else None
        )
        self._previous_limit: int | None = None

    @property
    def backend_name(self) -> str:
        return "mock-battery"

    def probe(self) -> list[CapabilityRecord]:
        now = time.monotonic()
        caps: list[CapabilityRecord] = []

        # Battery charge is always readable
        caps.append(CapabilityRecord(
            feature_id=FeatureId.BATTERY_CHARGE,
            status=FeatureStatus.SUPPORTED,
            interface=self.backend_name,
            readable=True,
            writable=False,
            current_value=self._config.battery_percent,
            supported_range=(0, 100),
            last_probe_time=now,
            confidence="mock",
        ))

        caps.append(CapabilityRecord(
            feature_id=FeatureId.BATTERY_STATE,
            status=FeatureStatus.SUPPORTED,
            interface=self.backend_name,
            readable=True,
            writable=False,
            current_value=self._config.battery_state,
            last_probe_time=now,
            confidence="mock",
        ))

        # Charge limit
        if self._config.model == MockModel.UNSUPPORTED:
            caps.append(CapabilityRecord(
                feature_id=FeatureId.CHARGE_LIMIT,
                status=FeatureStatus.UNSUPPORTED,
                interface=self.backend_name,
                last_probe_time=now,
            ))
        else:
            writable = self._config.model != MockModel.UNSUPPORTED
            caps.append(CapabilityRecord(
                feature_id=FeatureId.CHARGE_LIMIT,
                status=FeatureStatus.SUPPORTED,
                interface=self.backend_name,
                readable=True,
                writable=writable,
                current_value=self._charge_limit,
                supported_range=self._config.charge_limit_range,
                last_probe_time=now,
                confidence="mock",
            ))

        return caps

    def read_charge_percent(self) -> SensorReading:
        return SensorReading(
            self._config.battery_percent, "%",
            ValueQuality.MEASURED, source=self.backend_name,
        )

    def read_charge_state(self) -> str:
        return self._config.battery_state

    def get_charge_limit(self) -> int | None:
        return self._charge_limit

    def set_charge_limit(self, percent: int) -> WriteResult:
        if self._charge_limit is None:
            return WriteResult(
                success=False,
                feature=FeatureId.CHARGE_LIMIT,
                requested_value=percent,
                backend=self.backend_name,
                error="Charge limit not supported on this device",
            )

        low, high = self._config.charge_limit_range
        if percent < low or percent > high:
            return WriteResult(
                success=False,
                feature=FeatureId.CHARGE_LIMIT,
                requested_value=percent,
                backend=self.backend_name,
                error=f"Charge limit {percent}% outside range [{low}, {high}]",
            )

        self._previous_limit = self._charge_limit
        self._charge_limit = percent
        return WriteResult(
            success=True,
            feature=FeatureId.CHARGE_LIMIT,
            requested_value=percent,
            actual_value=percent,
            verified=True,
            backend=self.backend_name,
        )

    def get_charge_limit_range(self) -> tuple[int, int] | None:
        if self._charge_limit is None:
            return None
        return self._config.charge_limit_range


# ---------------------------------------------------------------------------
# Mock keyboard backend
# ---------------------------------------------------------------------------

class MockKeyboardBackend(KeyboardBackend):
    """Mock keyboard backlight and RGB control."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._brightness = 80
        self._zones: dict[int, RGBColor] = {
            0: RGBColor(0, 120, 255),
            1: RGBColor(0, 120, 255),
            2: RGBColor(0, 120, 255),
            3: RGBColor(0, 120, 255),
        }
        self._effect = KeyboardEffect.STATIC
        self._effect_speed = 50
        self._available = config.model in (
            MockModel.VERIFIED, MockModel.COMMUNITY, MockModel.BIOS_MISMATCH,
        )

    @property
    def backend_name(self) -> str:
        return "mock-keyboard"

    def probe(self) -> list[CapabilityRecord]:
        now = time.monotonic()

        if not self._available:
            return [
                CapabilityRecord(
                    feature_id=fid,
                    status=FeatureStatus.UNSUPPORTED,
                    interface=self.backend_name,
                    last_probe_time=now,
                )
                for fid in (
                    FeatureId.KEYBOARD_BRIGHTNESS,
                    FeatureId.KEYBOARD_RGB,
                    FeatureId.KEYBOARD_EFFECT,
                )
            ]

        return [
            CapabilityRecord(
                feature_id=FeatureId.KEYBOARD_BRIGHTNESS,
                status=FeatureStatus.SUPPORTED,
                interface=self.backend_name,
                readable=True,
                writable=True,
                current_value=self._brightness,
                supported_range=(0, 100),
                last_probe_time=now,
                confidence="mock",
            ),
            CapabilityRecord(
                feature_id=FeatureId.KEYBOARD_RGB,
                status=FeatureStatus.SUPPORTED,
                interface=self.backend_name,
                readable=True,
                writable=True,
                current_value=4,
                last_probe_time=now,
                confidence="mock",
            ),
            CapabilityRecord(
                feature_id=FeatureId.KEYBOARD_EFFECT,
                status=FeatureStatus.SUPPORTED,
                interface=self.backend_name,
                readable=True,
                writable=True,
                current_value=self._effect.value,
                supported_values=["static", "breathing", "off"],
                last_probe_time=now,
                confidence="mock",
            ),
        ]

    def get_brightness(self) -> int:
        return self._brightness

    def set_brightness(self, level: int) -> WriteResult:
        if not self._available:
            return WriteResult(
                success=False,
                feature=FeatureId.KEYBOARD_BRIGHTNESS,
                requested_value=level,
                backend=self.backend_name,
                error="Keyboard backlight not available",
            )
        if level < 0 or level > 100:
            return WriteResult(
                success=False,
                feature=FeatureId.KEYBOARD_BRIGHTNESS,
                requested_value=level,
                backend=self.backend_name,
                error=f"Brightness {level} outside range [0, 100]",
            )
        self._brightness = level
        return WriteResult(
            success=True,
            feature=FeatureId.KEYBOARD_BRIGHTNESS,
            requested_value=level,
            actual_value=level,
            verified=True,
            backend=self.backend_name,
        )

    def get_zone_count(self) -> int:
        return 4 if self._available else 0

    def get_zone_color(self, zone_id: int) -> RGBColor | None:
        return self._zones.get(zone_id)

    def set_zone_color(self, zone_id: int, color: RGBColor) -> WriteResult:
        if not self._available:
            return WriteResult(
                success=False,
                feature=FeatureId.KEYBOARD_RGB,
                requested_value=color.to_hex(),
                backend=self.backend_name,
                error="Keyboard RGB not available",
            )
        if zone_id not in self._zones:
            return WriteResult(
                success=False,
                feature=FeatureId.KEYBOARD_RGB,
                requested_value=color.to_hex(),
                backend=self.backend_name,
                error=f"Invalid zone: {zone_id}",
            )
        self._zones[zone_id] = color
        return WriteResult(
            success=True,
            feature=FeatureId.KEYBOARD_RGB,
            requested_value=color.to_hex(),
            actual_value=color.to_hex(),
            verified=True,
            backend=self.backend_name,
        )

    def set_effect(self, effect: KeyboardEffect, speed: int = 50) -> WriteResult:
        if not self._available:
            return WriteResult(
                success=False,
                feature=FeatureId.KEYBOARD_EFFECT,
                requested_value=effect.value,
                backend=self.backend_name,
                error="Keyboard effects not available",
            )
        self._effect = effect
        self._effect_speed = speed
        return WriteResult(
            success=True,
            feature=FeatureId.KEYBOARD_EFFECT,
            requested_value=effect.value,
            actual_value=effect.value,
            verified=True,
            backend=self.backend_name,
        )

    def get_supported_effects(self) -> list[KeyboardEffect]:
        if not self._available:
            return []
        return [KeyboardEffect.STATIC, KeyboardEffect.BREATHING, KeyboardEffect.OFF]


# ---------------------------------------------------------------------------
# Mock system info backend
# ---------------------------------------------------------------------------

class MockSystemInfoBackend(SystemInfoBackend):
    """Mock system information backend."""

    def __init__(self, config: MockConfig) -> None:
        self._config = config
        self._sim = _SensorSimulator(config)
        self._start_time = time.monotonic()

    @property
    def backend_name(self) -> str:
        return "mock-system-info"

    def read_dmi(self) -> DMIInfo:
        return _MOCK_DMI.get(self._config.model, _MOCK_DMI[MockModel.UNSUPPORTED])

    def read_cpu_util(self) -> SensorReading:
        return SensorReading(
            self._sim.cpu_util(), "%",
            ValueQuality.MEASURED, source=self.backend_name,
        )

    def read_ram_usage(self) -> tuple[SensorReading, SensorReading, SensorReading]:
        used = self._config.ram_used_gb * 1024 * 1024 * 1024
        total = self._config.ram_total_gb * 1024 * 1024 * 1024
        util = (self._config.ram_used_gb / self._config.ram_total_gb) * 100.0

        return (
            SensorReading(used, "B", ValueQuality.MEASURED, source=self.backend_name),
            SensorReading(total, "B", ValueQuality.MEASURED, source=self.backend_name),
            SensorReading(util, "%", ValueQuality.MEASURED, source=self.backend_name),
        )

    def read_gpu_util(self) -> SensorReading:
        if self._config.gpu_suspended:
            return SensorReading(None, "%", ValueQuality.UNAVAILABLE, source=self.backend_name)
        return SensorReading(
            self._sim.gpu_util(), "%",
            ValueQuality.MEASURED, source=self.backend_name,
        )

    def read_uptime(self) -> float:
        return time.monotonic() - self._start_time + 3600.0  # Simulated 1h base

    def is_gpu_suspended(self) -> bool:
        return self._config.gpu_suspended

    def get_kernel_version(self) -> str:
        return "6.8.0-40-generic"

    def get_distro_info(self) -> str:
        return "Ubuntu 26.04 LTS"


# ---------------------------------------------------------------------------
# Mock backend factory
# ---------------------------------------------------------------------------

def create_mock_backends(
    config: MockConfig | None = None,
) -> dict[str, Any]:
    """Create a complete set of mock backends.

    Args:
        config: Mock configuration. Defaults to VERIFIED model.

    Returns:
        Dictionary with keys: sensor, fan_control, profile, battery,
        keyboard, system_info, and the config itself.
    """
    if config is None:
        config = MockConfig()

    return {
        "config": config,
        "sensor": MockSensorBackend(config),
        "fan_control": MockFanControlBackend(config),
        "profile": MockProfileBackend(config),
        "battery": MockBatteryBackend(config),
        "keyboard": MockKeyboardBackend(config),
        "system_info": MockSystemInfoBackend(config),
    }


class MockHardwareManager:
    """Convenience wrapper around mock hardware backends."""

    def __init__(self, config: MockConfig | None = None) -> None:
        self.backends = create_mock_backends(config)
        self.sensor = self.backends["sensor"]
        self.fan = self.backends["fan_control"]
        self.profile = self.backends["profile"]
        self.battery = self.backends["battery"]
        self.keyboard = self.backends["keyboard"]
        self.system_info = self.backends["system_info"]
        self.config = self.backends["config"]


"""Unit tests for sctrl.models."""

from __future__ import annotations

import pytest
from sctrl.models import (
    CapabilityRecord,
    DaemonState,
    DMIInfo,
    FanCurve,
    FanCurvePoint,
    FanLease,
    FanMode,
    FeatureId,
    FeatureStatus,
    LogicalProfile,
    ProfileState,
    RGBColor,
    SensorReading,
    SupportTier,
    TelemetrySnapshot,
    ValueQuality,
)


def test_rgb_color_validation() -> None:
    c = RGBColor(255, 128, 0)
    assert c.r == 255
    assert c.g == 128
    assert c.b == 0
    assert c.to_hex() == "#ff8000"
    assert c.to_dict() == {"r": 255, "g": 128, "b": 0}

    with pytest.raises(ValueError):
        RGBColor(256, 0, 0)

    with pytest.raises(ValueError):
        RGBColor(0, -1, 0)


def test_sensor_reading() -> None:
    reading = SensorReading(value=55.5, unit="C", quality=ValueQuality.MEASURED, source="hwmon")
    assert reading.is_available is True
    assert reading.value == 55.5
    d = reading.to_dict()
    assert d["value"] == 55.5
    assert d["unit"] == "C"
    assert d["quality"] == "measured"

    unavail = SensorReading(value=None, unit="C", quality=ValueQuality.UNAVAILABLE)
    assert unavail.is_available is False


def test_fan_curve_and_lease() -> None:
    curve = FanCurve(
        points=[FanCurvePoint(40, 20), FanCurvePoint(60, 50), FanCurvePoint(80, 100)],
        hysteresis_c=3,
        min_dwell_s=5,
    )
    d = curve.to_dict()
    assert len(d["points"]) == 3
    assert d["hysteresis_c"] == 3

    lease = FanLease(holder="user", fan_target="both", mode=FanMode.MAX, expires_at=1000.0)
    assert lease.holder == "user"
    assert lease.fan_target == "both"


def test_capability_record_serialization() -> None:
    cap = CapabilityRecord(
        feature_id=FeatureId.CPU_TEMP,
        status=FeatureStatus.SUPPORTED,
        interface="/sys/class/hwmon/hwmon0/temp1_input",
        readable=True,
        writable=False,
        current_value=45.0,
        tier=SupportTier.VERIFIED,
    )
    d = cap.to_dict()
    assert d["feature_id"] == "cpu_temp"
    assert d["status"] == "supported"
    assert d["readable"] is True
    assert d["writable"] is False
    assert d["tier"] == "verified"


def test_daemon_state_and_telemetry() -> None:
    dmi = DMIInfo(product_name="PHN16-72", vendor="Acer")
    state = DaemonState(
        tier=SupportTier.COMMUNITY,
        dmi=dmi,
        fan_mode=FanMode.AUTO,
    )
    d = state.to_dict()
    assert d["tier"] == "community"
    assert d["dmi"]["product_name"] == "PHN16-72"

    snap = TelemetrySnapshot(uptime_seconds=3600.0)
    snap_dict = snap.to_dict()
    assert snap_dict["uptime_seconds"] == 3600.0

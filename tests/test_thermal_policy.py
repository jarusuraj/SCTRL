"""Unit tests for daemon.control.thermal_policy."""

from __future__ import annotations

import pytest
from sctrl.models import SensorReading, ValueQuality
from daemon.control.thermal_policy import ThermalAlert, ThermalPolicy, ThermalState, ThermalThresholds


def test_thermal_policy_transitions() -> None:
    emergency_events: list[bool] = []

    def on_emergency(active: bool) -> None:
        emergency_events.append(active)

    thresholds = ThermalThresholds(
        cpu_warn_c=80,
        cpu_critical_c=90,
        gpu_warn_c=75,
        gpu_critical_c=85,
    )
    policy = ThermalPolicy(thresholds=thresholds)
    policy.set_emergency_callback(on_emergency)

    # 1. Normal temperature (50°C)
    reading_normal = SensorReading(50.0, "C", ValueQuality.MEASURED)
    alerts = policy.evaluate(reading_normal, reading_normal, now=10.0)
    assert policy.cpu_state == ThermalState.NORMAL
    assert len(alerts) == 0

    # 2. Warning temperature (82°C)
    reading_warn = SensorReading(82.0, "C", ValueQuality.MEASURED)
    alerts = policy.evaluate(reading_warn, reading_normal, now=11.0)
    assert policy.cpu_state == ThermalState.WARNING
    assert len(alerts) == 1
    assert alerts[0].state == ThermalState.WARNING

    # 3. Critical temperature (92°C) -> Triggers emergency callback
    reading_crit = SensorReading(92.0, "C", ValueQuality.MEASURED)
    alerts = policy.evaluate(reading_crit, reading_normal, now=12.0)
    assert policy.cpu_state == ThermalState.CRITICAL
    assert len(alerts) == 1
    assert alerts[0].state == ThermalState.CRITICAL
    assert emergency_events == [True]

    # 4. Temperature cools down to normal (60°C) -> Clears emergency callback
    alerts = policy.evaluate(reading_normal, reading_normal, now=13.0)
    assert policy.cpu_state == ThermalState.NORMAL
    assert emergency_events == [True, False]

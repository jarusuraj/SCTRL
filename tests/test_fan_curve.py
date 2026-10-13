"""Unit tests for daemon.control.fan_curve."""

from __future__ import annotations

import pytest
from sctrl.errors import ValidationError
from sctrl.models import FanCurve, FanCurvePoint
from daemon.control.fan_curve import FanCurveController, validate_fan_curve_strict


def test_validate_fan_curve_strict() -> None:
    # Valid curve
    curve = FanCurve(
        points=[
            FanCurvePoint(40, 20),
            FanCurvePoint(55, 45),
            FanCurvePoint(70, 70),
            FanCurvePoint(85, 100),
        ],
        hysteresis_c=3,
        min_dwell_s=5,
        below_first_speed=20,
    )
    validate_fan_curve_strict(curve, min_speed=0, max_speed=100)


    # Less than 2 points -> invalid
    with pytest.raises(ValidationError):
        validate_fan_curve_strict(FanCurve(points=[FanCurvePoint(50, 50)]))

    # Non-monotonic temperature -> invalid
    with pytest.raises(ValidationError):
        validate_fan_curve_strict(
            FanCurve(points=[FanCurvePoint(60, 30), FanCurvePoint(50, 60)])
        )

    # Non-monotonic speed (decreasing fan speed as temperature rises) -> invalid
    with pytest.raises(ValidationError):
        validate_fan_curve_strict(
            FanCurve(points=[FanCurvePoint(40, 50), FanCurvePoint(70, 30)])
        )

    # Out of range speed -> invalid
    with pytest.raises(ValidationError):
        validate_fan_curve_strict(
            FanCurve(points=[FanCurvePoint(40, -5), FanCurvePoint(70, 100)])
        )


def test_fan_curve_interpolation() -> None:
    curve = FanCurve(
        points=[
            FanCurvePoint(40, 20),
            FanCurvePoint(80, 100),
        ],
        hysteresis_c=0,
        min_dwell_s=0,
        below_first_speed=20,
        above_last_speed=100,
    )
    ctrl = FanCurveController(curve)

    # Exactly midpoint: 60°C -> 60%
    speed = ctrl.compute_speed(60.0, now=10.0)
    assert speed == 60

    # Below lowest point: 30°C -> 20%
    assert ctrl.compute_speed(30.0, now=11.0) == 20

    # Above highest point: 90°C -> 100%
    assert ctrl.compute_speed(90.0, now=12.0) == 100

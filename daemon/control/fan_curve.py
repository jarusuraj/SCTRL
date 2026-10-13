"""Fan curve validation and interpolation for SCTRL.

Validates fan curves against safety constraints and provides linear
interpolation between curve points.
"""

from __future__ import annotations

from sctrl.errors import ValidationError
from sctrl.models import FanCurve, FanCurvePoint


def validate_fan_curve(
    curve: FanCurve,
    min_speed: int = 0,
    max_speed: int = 100,
    min_temp: int = 0,
    max_temp: int = 120,
) -> list[str]:
    """Validate a fan curve and return a list of error messages.

    An empty list means the curve is valid.

    Rules:
    - At least two points.
    - Temperatures monotonically increasing.
    - Speeds non-decreasing.
    - All values within bounds.
    - Hysteresis non-negative and less than smallest temperature gap.
    - Min dwell time non-negative.
    """
    errors: list[str] = []

    if len(curve.points) < 2:
        errors.append(f"Fan curve requires at least 2 points, got {len(curve.points)}")
        return errors  # No point checking further

    # Check bounds
    for i, pt in enumerate(curve.points):
        if pt.temp_c < min_temp or pt.temp_c > max_temp:
            errors.append(
                f"Point {i}: temperature {pt.temp_c}C outside range "
                f"[{min_temp}, {max_temp}]"
            )
        if pt.speed_percent < min_speed or pt.speed_percent > max_speed:
            errors.append(
                f"Point {i}: speed {pt.speed_percent}% outside range "
                f"[{min_speed}, {max_speed}]"
            )

    # Check monotonically increasing temperatures
    for i in range(1, len(curve.points)):
        if curve.points[i].temp_c <= curve.points[i - 1].temp_c:
            errors.append(
                f"Points {i - 1} and {i}: temperatures must be strictly "
                f"increasing ({curve.points[i - 1].temp_c}C >= {curve.points[i].temp_c}C)"
            )

    # Check non-decreasing speeds
    for i in range(1, len(curve.points)):
        if curve.points[i].speed_percent < curve.points[i - 1].speed_percent:
            errors.append(
                f"Points {i - 1} and {i}: speeds must be non-decreasing "
                f"({curve.points[i - 1].speed_percent}% > {curve.points[i].speed_percent}%)"
            )

    # Check below_first_speed and above_last_speed bounds
    if curve.below_first_speed < min_speed or curve.below_first_speed > max_speed:
        errors.append(
            f"below_first_speed {curve.below_first_speed}% outside range "
            f"[{min_speed}, {max_speed}]"
        )
    if curve.above_last_speed < min_speed or curve.above_last_speed > max_speed:
        errors.append(
            f"above_last_speed {curve.above_last_speed}% outside range "
            f"[{min_speed}, {max_speed}]"
        )

    # Check hysteresis
    if curve.hysteresis_c < 0:
        errors.append(f"Hysteresis must be non-negative, got {curve.hysteresis_c}")
    elif len(curve.points) >= 2:
        min_gap = min(
            curve.points[i].temp_c - curve.points[i - 1].temp_c
            for i in range(1, len(curve.points))
            if curve.points[i].temp_c > curve.points[i - 1].temp_c
        ) if any(
            curve.points[i].temp_c > curve.points[i - 1].temp_c
            for i in range(1, len(curve.points))
        ) else 0

        if min_gap > 0 and curve.hysteresis_c >= min_gap:
            errors.append(
                f"Hysteresis {curve.hysteresis_c}C must be less than smallest "
                f"temperature gap ({min_gap}C)"
            )

    # Check min_dwell_s
    if curve.min_dwell_s < 0:
        errors.append(f"min_dwell_s must be non-negative, got {curve.min_dwell_s}")

    return errors


def validate_fan_curve_strict(
    curve: FanCurve,
    min_speed: int = 0,
    max_speed: int = 100,
    min_temp: int = 0,
    max_temp: int = 120,
) -> None:
    """Validate and raise ValidationError if invalid."""
    errors = validate_fan_curve(curve, min_speed, max_speed, min_temp, max_temp)
    if errors:
        raise ValidationError(
            f"Invalid fan curve: {'; '.join(errors)}",
            field="fan_curve",
        )


def interpolate_fan_speed(curve: FanCurve, temp_c: float) -> int:
    """Compute the target fan speed for a given temperature.

    Uses linear interpolation between points.
    Below the first point: returns below_first_speed.
    Above the last point: returns above_last_speed.

    Args:
        curve: Validated fan curve.
        temp_c: Current temperature in Celsius.

    Returns:
        Target fan speed percentage.
    """
    if not curve.points:
        return curve.above_last_speed

    if temp_c <= curve.points[0].temp_c:
        return curve.below_first_speed

    if temp_c >= curve.points[-1].temp_c:
        return curve.above_last_speed

    # Find the two enclosing points
    for i in range(1, len(curve.points)):
        if temp_c <= curve.points[i].temp_c:
            p0 = curve.points[i - 1]
            p1 = curve.points[i]
            temp_range = p1.temp_c - p0.temp_c
            if temp_range == 0:
                return p1.speed_percent

            fraction = (temp_c - p0.temp_c) / temp_range
            speed = p0.speed_percent + fraction * (p1.speed_percent - p0.speed_percent)
            return max(0, min(100, round(speed)))

    return curve.above_last_speed


class FanCurveController:
    """Applies a fan curve with hysteresis and dwell-time protection.

    Prevents rapid fan speed oscillation by requiring temperature changes
    to exceed the hysteresis threshold and enforcing minimum dwell time
    between speed changes.
    """

    def __init__(self, curve: FanCurve) -> None:
        self._curve = curve
        self._last_speed: int | None = None
        self._last_change_time: float = 0.0
        self._last_temp: float = 0.0
        self._increasing: bool = True

    @property
    def curve(self) -> FanCurve:
        return self._curve

    def update_curve(self, curve: FanCurve) -> None:
        """Replace the active curve. Resets hysteresis state."""
        self._curve = curve
        self._last_speed = None
        self._last_change_time = 0.0

    def compute_speed(
        self,
        temp_c: float,
        current_time: float | None = None,
        now: float | None = None,
    ) -> int:
        """Compute the target speed with hysteresis and dwell time.

        Args:
            temp_c: Current temperature.
            current_time: Monotonic timestamp (optional, defaults to time.monotonic).
            now: Alias for current_time.

        Returns:
            Target fan speed percentage.
        """
        import time
        ts = current_time if current_time is not None else (now if now is not None else time.monotonic())
        raw_speed = interpolate_fan_speed(self._curve, temp_c)

        if self._last_speed is None:
            self._last_speed = raw_speed
            self._last_change_time = ts
            self._last_temp = temp_c
            return raw_speed

        # Check dwell time
        elapsed = ts - self._last_change_time
        if elapsed < self._curve.min_dwell_s:
            return self._last_speed

        # Apply hysteresis
        temp_delta = temp_c - self._last_temp
        if abs(temp_delta) < self._curve.hysteresis_c:
            # Temperature hasn't changed enough; keep current speed
            # unless the raw speed is higher (temperature increasing)
            if raw_speed > self._last_speed:
                self._last_speed = raw_speed
                self._last_change_time = ts
                self._last_temp = temp_c
            return self._last_speed

        # Temperature changed sufficiently
        self._last_speed = raw_speed
        self._last_change_time = ts
        self._last_temp = temp_c
        return raw_speed

    def reset(self) -> None:
        """Reset controller state."""
        self._last_speed = None
        self._last_change_time = 0.0
        self._last_temp = 0.0

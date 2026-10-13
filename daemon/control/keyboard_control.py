"""Keyboard backlight and RGB lighting controller for SCTRL daemon.

Provides multi-zone RGB, brightness adjustment, and lighting effects control.
"""

from __future__ import annotations

import logging
from typing import Any

from sctrl.constants import DEFAULT_KEYBOARD_BRIGHTNESS
from sctrl.errors import HardwareWriteError, UnsupportedError, ValidationError
from sctrl.models import (
    FeatureId,
    FeatureStatus,
    KeyboardEffect,
    KeyboardZone,
    RGBColor,
)
from daemon.capability_registry import CapabilityRegistry
from daemon.hardware.base import KeyboardBackend, WriteResult

logger = logging.getLogger("sctrld.keyboard_control")


class KeyboardController:
    """Controls keyboard backlight brightness, zones, and effects."""

    def __init__(
        self,
        backend: KeyboardBackend,
        registry: CapabilityRegistry,
    ) -> None:
        self._backend = backend
        self._registry = registry
        self._zone_colors: dict[int, RGBColor] = {}
        self._current_effect: KeyboardEffect = KeyboardEffect.STATIC
        self._current_speed: int = 50

    @property
    def is_brightness_supported(self) -> bool:
        cap = self._registry.get(FeatureId.KEYBOARD_BRIGHTNESS)
        return cap is not None and cap.status == FeatureStatus.SUPPORTED and cap.writable

    @property
    def is_rgb_supported(self) -> bool:
        cap = self._registry.get(FeatureId.KEYBOARD_RGB)
        return cap is not None and cap.status == FeatureStatus.SUPPORTED and cap.writable

    @property
    def zone_count(self) -> int:
        if not self.is_rgb_supported:
            return 0
        return self._backend.get_zone_count()

    def get_brightness(self) -> int:
        if not self.is_brightness_supported:
            return 0
        return self._backend.get_brightness()

    def set_brightness(self, level: int) -> WriteResult:
        """Set keyboard backlight brightness (0-100)."""
        self._registry.check_write_permission(FeatureId.KEYBOARD_BRIGHTNESS)
        if not self.is_brightness_supported:
            raise UnsupportedError("Keyboard brightness control is not supported on this system")

        if not 0 <= level <= 100:
            raise ValidationError(
                f"Brightness level {level} must be between 0 and 100",
                field="brightness",
                value=level,
            )

        logger.info("Setting keyboard brightness to %d%%", level)
        result = self._backend.set_brightness(level)
        if result.success:
            self._registry.update_value(FeatureId.KEYBOARD_BRIGHTNESS, level)
        return result

    def get_supported_effects(self) -> list[KeyboardEffect]:
        if not self.is_rgb_supported:
            return []
        return self._backend.get_supported_effects()

    def get_zone_color(self, zone_id: int) -> RGBColor | None:
        if not self.is_rgb_supported:
            return None
        return self._backend.get_zone_color(zone_id)

    def set_zone_color(self, zone_id: int, color: RGBColor) -> WriteResult:
        """Set RGB color for a specific zone (0-indexed)."""
        self._registry.check_write_permission(FeatureId.KEYBOARD_RGB)
        if not self.is_rgb_supported:
            raise UnsupportedError("Keyboard RGB control is not supported on this system")

        max_zones = self.zone_count
        if not 0 <= zone_id < max_zones:
            raise ValidationError(
                f"Zone ID {zone_id} is invalid (total zones: {max_zones})",
                field="zone_id",
                value=zone_id,
            )

        logger.info("Setting keyboard zone %d color to %s", zone_id, color.to_hex())
        result = self._backend.set_zone_color(zone_id, color)
        if result.success:
            self._zone_colors[zone_id] = color
        return result

    def set_all_zones_color(self, color: RGBColor) -> list[WriteResult]:
        """Set all zones to the same color."""
        results: list[WriteResult] = []
        for z in range(self.zone_count):
            results.append(self.set_zone_color(z, color))
        return results

    def set_effect(self, effect: KeyboardEffect, speed: int = 50) -> WriteResult:
        """Set keyboard animation effect and speed (0-100)."""
        self._registry.check_write_permission(FeatureId.KEYBOARD_EFFECT)
        if not self.is_rgb_supported:
            raise UnsupportedError("Keyboard effects are not supported on this system")

        supported = self.get_supported_effects()
        if effect not in supported:
            raise UnsupportedError(f"Keyboard effect '{effect.value}' not supported")

        if not 0 <= speed <= 100:
            raise ValidationError("Effect speed must be between 0 and 100", field="speed", value=speed)

        logger.info("Setting keyboard effect to %s with speed %d", effect.value, speed)
        result = self._backend.set_effect(effect, speed)
        if result.success:
            self._current_effect = effect
            self._current_speed = speed
            self._registry.update_value(FeatureId.KEYBOARD_EFFECT, effect.value)
        return result

"""Acer keyboard backlight and RGB controller backend.

Interacts with sysfs led class or acer-wmi / linuwu-sense rgb nodes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sctrl.constants import SYSFS_LEDS
from sctrl.models import (
    CapabilityRecord,
    FeatureId,
    FeatureStatus,
    KeyboardEffect,
    RGBColor,
)
from daemon.hardware.base import KeyboardBackend, WriteResult

logger = logging.getLogger("sctrld.rgb")


class AcerKeyboardBackend(KeyboardBackend):
    """Controls keyboard backlight brightness and 4-zone RGB."""

    def __init__(self, leds_root: str | Path = SYSFS_LEDS) -> None:
        self._leds_root = Path(leds_root)
        self._brightness_file: Path | None = None
        self._max_brightness = 100
        self._current_brightness = 100
        self._zones: dict[int, RGBColor] = {
            0: RGBColor(0, 120, 255),
            1: RGBColor(0, 120, 255),
            2: RGBColor(0, 120, 255),
            3: RGBColor(0, 120, 255),
        }
        self._current_effect = KeyboardEffect.STATIC

    @property
    def backend_name(self) -> str:
        return "acer_keyboard"

    def probe(self) -> list[CapabilityRecord]:
        records: list[CapabilityRecord] = []
        if self._leds_root.exists():
            for led_dir in self._leds_root.glob("*kbd_backlight*"):
                bfile = led_dir / "brightness"
                if bfile.exists():
                    self._brightness_file = bfile
                    max_bfile = led_dir / "max_brightness"
                    if max_bfile.exists():
                        try:
                            self._max_brightness = int(max_bfile.read_text().strip())
                        except Exception:
                            pass
                    records.append(CapabilityRecord(
                        feature_id=FeatureId.KEYBOARD_BRIGHTNESS,
                        status=FeatureStatus.SUPPORTED,
                        interface=str(bfile),
                        readable=True,
                        writable=True,
                        supported_range=(0, 100),
                    ))
                    break

        return records

    def get_brightness(self) -> int:
        if self._brightness_file and self._brightness_file.exists():
            try:
                val = int(self._brightness_file.read_text().strip())
                if self._max_brightness > 0:
                    return int((val / self._max_brightness) * 100)
            except Exception:
                pass
        return self._current_brightness

    def set_brightness(self, level: int) -> WriteResult:
        if not self._brightness_file or not self._brightness_file.exists():
            return WriteResult(
                success=False,
                feature=FeatureId.KEYBOARD_BRIGHTNESS,
                requested_value=level,
                verified=False,
                backend=self.backend_name,
                error="Keyboard backlight sysfs file does not exist",
            )
        try:
            scaled = int((level / 100.0) * self._max_brightness)
            self._brightness_file.write_text(str(scaled))
            # Read-back verification
            actual = self.get_brightness()
            verified = (actual == level)
            if verified:
                self._current_brightness = actual
            return WriteResult(
                success=verified,
                feature=FeatureId.KEYBOARD_BRIGHTNESS,
                requested_value=level,
                actual_value=actual,
                verified=verified,
                backend=self.backend_name,
                error="" if verified else f"Readback mismatch: wrote {level}%, got {actual}%",
            )
        except Exception as e:
            return WriteResult(
                success=False,
                feature=FeatureId.KEYBOARD_BRIGHTNESS,
                requested_value=level,
                verified=False,
                backend=self.backend_name,
                error=str(e),
            )

    def get_zone_count(self) -> int:
        return 0

    def get_zone_color(self, zone_id: int) -> RGBColor | None:
        return None

    def set_zone_color(self, zone_id: int, color: RGBColor) -> WriteResult:
        return WriteResult(
            success=False,
            feature=FeatureId.KEYBOARD_RGB,
            requested_value=color.to_hex(),
            verified=False,
            backend=self.backend_name,
            error="Generic sysfs led backend does not support multi-zone RGB. Requires linuwu-sense.",
        )

    def set_effect(self, effect: KeyboardEffect, speed: int = 50) -> WriteResult:
        return WriteResult(
            success=False,
            feature=FeatureId.KEYBOARD_EFFECT,
            requested_value=effect.value,
            verified=False,
            backend=self.backend_name,
            error="Generic sysfs led backend does not support lighting effects. Requires linuwu-sense.",
        )

    def get_supported_effects(self) -> list[KeyboardEffect]:
        return []


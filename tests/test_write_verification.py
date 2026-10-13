"""Tests verifying read-back verification and failure behavior for hardware writes."""

from __future__ import annotations

from pathlib import Path
import pytest

from sctrl.models import FanMode, FeatureId, KeyboardEffect, RGBColor
from daemon.hardware.acer_wmi import PlatformProfileBackend
from daemon.hardware.battery import SysfsBatteryBackend
from daemon.hardware.linuwu_sense import LinuwuSenseBackend
from daemon.hardware.rgb import AcerKeyboardBackend


def test_missing_target_file_returns_failure(tmp_path: Path) -> None:
    """When the underlying sysfs control file is missing, write returns success=False and does not crash."""
    non_existent = tmp_path / "does_not_exist"

    # PlatformProfileBackend
    prof_backend = PlatformProfileBackend(profile_file=non_existent)
    res_prof = prof_backend.set_profile("performance")
    assert res_prof.success is False
    assert res_prof.verified is False
    assert "not exist" in res_prof.error.lower() or "missing" in res_prof.error.lower()

    # BatteryBackend
    bat_backend = SysfsBatteryBackend(sysfs_root=non_existent)
    res_bat = bat_backend.set_charge_limit(80)
    assert res_bat.success is False
    assert res_bat.verified is False

    # KeyboardBackend
    kbd_backend = AcerKeyboardBackend(leds_root=non_existent)
    res_kbd = kbd_backend.set_brightness(50)
    assert res_kbd.success is False
    assert res_kbd.verified is False


def test_readback_mismatch_sets_verified_false(tmp_path: Path) -> None:
    """If the read-back value doesn't match the written value, verified must be False."""
    prof_file = tmp_path / "platform_profile"
    prof_file.write_text("quiet")

    # A backend where writing does not update the file (e.g. read-only firmware or mock hardware glitch)
    class GlitchedProfileBackend(PlatformProfileBackend):
        def set_profile(self, profile_value: str):
            # We don't update file
            return super().set_profile(profile_value)

    backend = GlitchedProfileBackend(profile_file=prof_file)
    # The file has 'quiet'. We request 'performance'. File remains 'quiet'.
    # Note: PlatformProfileBackend writes to file. Let's make the file read-only or readback mismatched.
    # We can test with a custom mock file or subclass:
    class StubbornFileBackend(PlatformProfileBackend):
        def get_current_profile(self) -> str:
            return "quiet"

    stubborn = StubbornFileBackend(profile_file=prof_file)
    res = stubborn.set_profile("performance")
    assert res.success is False
    assert res.verified is False
    assert "mismatch" in res.error.lower()


def test_in_memory_state_not_changed_before_write_succeeds(tmp_path: Path) -> None:
    """In-memory state must NOT be modified if hardware write fails."""
    non_existent = tmp_path / "non_existent"
    kbd_backend = AcerKeyboardBackend(leds_root=non_existent)
    
    original_brightness = kbd_backend.get_brightness()
    res = kbd_backend.set_brightness(25)
    assert res.success is False
    # In-memory brightness should remain unchanged
    assert kbd_backend.get_brightness() == original_brightness

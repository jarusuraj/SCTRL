"""Tests verifying that on UNSUPPORTED and DETECTED tiers zero backend writes occur."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from sctrl.errors import TierBlockedError
from sctrl.models import (
    CapabilityRecord,
    FeatureId,
    FeatureStatus,
    LogicalProfile,
    RGBColor,
    SupportTier,
)
from daemon.capability_registry import CapabilityRegistry
from daemon.service import SCTRLService


def test_unsupported_tier_blocks_all_writes_and_issues_zero_backend_writes(tmp_path: Path) -> None:
    """On UNSUPPORTED tier, every write method in SCTRLService must raise TierBlockedError

    and zero backend write methods must be called.
    """
    cfg_file = tmp_path / "unsupported_test.toml"
    service = SCTRLService(mock_mode=True, mock_model="unsupported", config_path=cfg_file)

    # Attach mock spies to backends to verify no write methods are called
    fan_mock = MagicMock()
    profile_mock = MagicMock()
    battery_mock = MagicMock()
    keyboard_mock = MagicMock()

    service._fans.set_mode_auto = fan_mock.set_mode_auto
    service._fans.set_mode_max = fan_mock.set_mode_max
    service._fans.set_fan_speed = fan_mock.set_fan_speed
    service._profiles.set_profile = profile_mock.set_profile
    service._battery.set_charge_limit = battery_mock.set_charge_limit
    service._keyboard.set_brightness = keyboard_mock.set_brightness
    service._keyboard.set_zone_color = keyboard_mock.set_zone_color
    service._keyboard.set_effect = keyboard_mock.set_effect

    assert service.get_state().tier == SupportTier.UNSUPPORTED

    # 1. Fan mode write -> blocked
    with pytest.raises(TierBlockedError):
        service.set_fan_mode("max")

    # 2. Fan mode auto -> blocked
    with pytest.raises(TierBlockedError):
        service.set_fan_mode("auto")

    # 3. Profile write -> blocked
    with pytest.raises(TierBlockedError):
        service.set_profile("performance")

    # 4. Battery charge limit write -> blocked
    with pytest.raises(TierBlockedError):
        service.set_charge_limit(80)

    # 5. Keyboard brightness write -> blocked
    with pytest.raises(TierBlockedError):
        service.set_keyboard_brightness(50)

    # 6. Keyboard zone color write -> blocked
    with pytest.raises(TierBlockedError):
        service.set_keyboard_zone_color(0, 255, 0, 0)

    # 7. Keyboard effect write -> blocked
    with pytest.raises(TierBlockedError):
        service.set_keyboard_effect("breathing", 50)

    # Assert all backend mocks were called exactly ZERO times
    assert fan_mock.set_mode_auto.call_count == 0
    assert fan_mock.set_mode_max.call_count == 0
    assert fan_mock.set_fan_speed.call_count == 0
    assert profile_mock.set_profile.call_count == 0
    assert battery_mock.set_charge_limit.call_count == 0
    assert keyboard_mock.set_brightness.call_count == 0
    assert keyboard_mock.set_zone_color.call_count == 0
    assert keyboard_mock.set_effect.call_count == 0


def test_detected_tier_blocks_unopted_writes_and_issues_zero_backend_writes(tmp_path: Path) -> None:
    """On DETECTED tier, driver-specific and unopted writes must raise TierBlockedError

    and zero backend write methods must be called.
    """
    cfg_file = tmp_path / "detected_test.toml"
    service = SCTRLService(mock_mode=True, mock_model="detected", config_path=cfg_file)

    fan_mock = MagicMock()
    profile_mock = MagicMock()
    battery_mock = MagicMock()
    keyboard_mock = MagicMock()

    service._fans.set_mode_auto = fan_mock.set_mode_auto
    service._fans.set_mode_max = fan_mock.set_mode_max
    service._fans.set_fan_speed = fan_mock.set_fan_speed
    service._profiles.set_profile = profile_mock.set_profile
    service._battery.set_charge_limit = battery_mock.set_charge_limit
    service._keyboard.set_brightness = keyboard_mock.set_brightness
    service._keyboard.set_zone_color = keyboard_mock.set_zone_color
    service._keyboard.set_effect = keyboard_mock.set_effect

    assert service.get_state().tier == SupportTier.DETECTED

    # Driver-specific: Fan control is prohibited entirely on DETECTED tier
    with pytest.raises(TierBlockedError):
        service.set_fan_mode("max")

    with pytest.raises(TierBlockedError):
        service.set_keyboard_brightness(50)

    with pytest.raises(TierBlockedError):
        service.set_keyboard_zone_color(0, 0, 255, 0)

    # Standard feature: Profile requires opt-in
    with pytest.raises(TierBlockedError):
        service.set_profile("performance")

    # Standard feature: Charge limit requires opt-in
    with pytest.raises(TierBlockedError):
        service.set_charge_limit(80)

    # Assert zero backend writes occurred
    assert fan_mock.set_mode_auto.call_count == 0
    assert fan_mock.set_mode_max.call_count == 0
    assert fan_mock.set_fan_speed.call_count == 0
    assert profile_mock.set_profile.call_count == 0
    assert battery_mock.set_charge_limit.call_count == 0
    assert keyboard_mock.set_brightness.call_count == 0
    assert keyboard_mock.set_zone_color.call_count == 0
    assert keyboard_mock.set_effect.call_count == 0

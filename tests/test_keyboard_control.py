"""Unit tests for daemon.control.keyboard_control."""

from __future__ import annotations

import pytest
from sctrl.errors import ValidationError
from sctrl.models import CapabilityRecord, FeatureId, FeatureStatus, KeyboardEffect, RGBColor, SupportTier
from daemon.capability_registry import CapabilityRegistry
from daemon.control.keyboard_control import KeyboardController
from daemon.hardware.mock import MockConfig, MockHardwareManager, MockModel


@pytest.fixture
def keyboard_controller() -> KeyboardController:
    hw = MockHardwareManager(MockConfig(model=MockModel.VERIFIED))
    reg = CapabilityRegistry()
    reg.set_tier(SupportTier.VERIFIED, "Verified model")
    reg.update_capabilities({
        FeatureId.KEYBOARD_BRIGHTNESS: CapabilityRecord(
            feature_id=FeatureId.KEYBOARD_BRIGHTNESS,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            supported_range=(0, 100),
            tier=SupportTier.VERIFIED,
        ),
        FeatureId.KEYBOARD_RGB: CapabilityRecord(
            feature_id=FeatureId.KEYBOARD_RGB,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            tier=SupportTier.VERIFIED,
        ),
        FeatureId.KEYBOARD_EFFECT: CapabilityRecord(
            feature_id=FeatureId.KEYBOARD_EFFECT,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            supported_values=["static", "breathing", "off"],
            tier=SupportTier.VERIFIED,
        ),
    })
    return KeyboardController(backend=hw.keyboard, registry=reg)


def test_keyboard_brightness(keyboard_controller: KeyboardController) -> None:
    assert keyboard_controller.is_brightness_supported is True
    res = keyboard_controller.set_brightness(50)
    assert res.success is True
    assert keyboard_controller.get_brightness() == 50

    with pytest.raises(ValidationError):
        keyboard_controller.set_brightness(150)


def test_keyboard_rgb_zones(keyboard_controller: KeyboardController) -> None:
    assert keyboard_controller.is_rgb_supported is True
    assert keyboard_controller.zone_count == 4

    # Zone 0 set to red
    res = keyboard_controller.set_zone_color(0, RGBColor(255, 0, 0))
    assert res.success is True
    assert keyboard_controller.get_zone_color(0) == RGBColor(255, 0, 0)

    # Invalid zone 10
    with pytest.raises(ValidationError):
        keyboard_controller.set_zone_color(10, RGBColor(0, 255, 0))


def test_keyboard_effects(keyboard_controller: KeyboardController) -> None:
    res = keyboard_controller.set_effect(KeyboardEffect.BREATHING, speed=75)
    assert res.success is True

"""Unit tests for daemon.control.battery_control."""

from __future__ import annotations

import pytest
from sctrl.errors import UnsupportedError, ValidationError
from sctrl.models import CapabilityRecord, FeatureId, FeatureStatus, SupportTier
from daemon.capability_registry import CapabilityRegistry
from daemon.control.battery_control import BatteryController
from daemon.hardware.mock import MockConfig, MockHardwareManager, MockModel


@pytest.fixture
def battery_controller() -> BatteryController:
    hw = MockHardwareManager(MockConfig(model=MockModel.VERIFIED))
    reg = CapabilityRegistry()
    reg.set_tier(SupportTier.VERIFIED, "Verified model")
    reg.update_capabilities({
        FeatureId.CHARGE_LIMIT: CapabilityRecord(
            feature_id=FeatureId.CHARGE_LIMIT,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            supported_range=(50, 100),
            tier=SupportTier.VERIFIED,
        ),
        FeatureId.BATTERY_CHARGE: CapabilityRecord(
            feature_id=FeatureId.BATTERY_CHARGE,
            status=FeatureStatus.SUPPORTED,
            readable=True,
            tier=SupportTier.VERIFIED,
        ),
    })
    return BatteryController(backend=hw.battery, registry=reg)


def test_battery_charge_limit(battery_controller: BatteryController) -> None:
    assert battery_controller.is_charge_limit_supported is True
    assert battery_controller.charge_limit_range == (50, 100)

    # Valid limit: 80%
    res = battery_controller.set_charge_limit(80)
    assert res.success is True
    assert battery_controller.get_current_limit() == 80

    # Valid limit: 100%
    res = battery_controller.set_charge_limit(100)
    assert res.success is True
    assert battery_controller.get_current_limit() == 100

    # Invalid limit: 40% (below 50%) -> ValidationError
    with pytest.raises(ValidationError):
        battery_controller.set_charge_limit(40)

    # Invalid limit: 110% (above 100%) -> ValidationError
    with pytest.raises(ValidationError):
        battery_controller.set_charge_limit(110)

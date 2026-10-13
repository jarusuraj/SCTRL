"""Unit tests for daemon.control.fan_control."""

from __future__ import annotations

import time
import pytest
from sctrl.models import CapabilityRecord, FanCurve, FanCurvePoint, FanMode, FeatureId, FeatureStatus, SupportTier
from daemon.capability_registry import CapabilityRegistry
from daemon.control.fan_control import FanControlManager
from daemon.hardware.mock import MockConfig, MockHardwareManager, MockModel


@pytest.fixture
def fan_manager() -> FanControlManager:
    hw = MockHardwareManager(MockConfig(model=MockModel.VERIFIED))
    reg = CapabilityRegistry()
    reg.set_tier(SupportTier.VERIFIED, "Verified model")
    reg.update_capabilities({
        FeatureId.FAN_MODE: CapabilityRecord(
            feature_id=FeatureId.FAN_MODE,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            tier=SupportTier.VERIFIED,
        ),
        FeatureId.FAN_CURVE: CapabilityRecord(
            feature_id=FeatureId.FAN_CURVE,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            tier=SupportTier.VERIFIED,
        ),
    })
    return FanControlManager(backend=hw.fan, registry=reg)


def test_fan_mode_auto_and_max(fan_manager: FanControlManager) -> None:
    # Auto
    res_auto = fan_manager.set_mode_auto("user")
    assert res_auto.success is True
    assert fan_manager.current_mode == FanMode.AUTO
    assert fan_manager.has_active_lease is False

    # Max (acquires lease)
    res_max = fan_manager.set_mode_max("user")
    assert res_max.success is True
    assert fan_manager.current_mode == FanMode.MAX
    assert fan_manager.has_active_lease is True
    assert fan_manager.lease_remaining_s > 0


def test_fan_lease_renewal(fan_manager: FanControlManager) -> None:
    fan_manager.set_mode_max("user")
    assert fan_manager.has_active_lease is True

    # Renew with same holder -> True
    assert fan_manager.renew_lease("user", duration_s=60) is True

    # Renew with different holder -> False
    assert fan_manager.renew_lease("other_user", duration_s=60) is False


def test_emergency_override(fan_manager: FanControlManager) -> None:
    fan_manager.set_mode_max("user")
    res = fan_manager.trigger_emergency_override("Critical CPU temp 98C")
    assert res.success is True
    assert fan_manager.emergency_override_active is True

    fan_manager.clear_emergency_override()
    assert fan_manager.emergency_override_active is False

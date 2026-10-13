"""Unit tests for daemon.control.profile_control."""

from __future__ import annotations

import pytest
from sctrl.errors import HardwareWriteError, UnsupportedError
from sctrl.models import CapabilityRecord, FeatureId, FeatureStatus, LogicalProfile, SupportTier
from daemon.capability_registry import CapabilityRegistry
from daemon.control.profile_control import ProfileManager
from daemon.hardware.mock import MockConfig, MockHardwareManager, MockModel


@pytest.fixture
def profile_manager() -> ProfileManager:
    hw = MockHardwareManager(MockConfig(model=MockModel.VERIFIED))
    reg = CapabilityRegistry()
    reg.set_tier(SupportTier.VERIFIED, "Verified model")
    reg.update_capabilities({
        FeatureId.PERFORMANCE_PROFILE: CapabilityRecord(
            feature_id=FeatureId.PERFORMANCE_PROFILE,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            supported_values=["quiet", "balanced", "performance", "turbo"],
            tier=SupportTier.VERIFIED,
        ),
    })
    return ProfileManager(backend=hw.profile, registry=reg)


def test_profile_switching(profile_manager: ProfileManager) -> None:
    assert profile_manager.is_supported is True
    avail = profile_manager.get_available_profiles()
    assert LogicalProfile.BALANCED in avail
    assert LogicalProfile.PERFORMANCE in avail
    assert LogicalProfile.TURBO in avail

    # Switch to performance
    res = profile_manager.set_profile(LogicalProfile.PERFORMANCE)
    assert res.success is True
    assert profile_manager.get_current_profile() == LogicalProfile.PERFORMANCE

    # Switch to turbo while explicitly on battery (is_ac_online=False) -> HardwareWriteError
    with pytest.raises(HardwareWriteError):
        profile_manager.set_profile(LogicalProfile.TURBO, is_ac_online=False)

    # Switch to turbo while on AC (is_ac_online=True) -> Success
    res_turbo = profile_manager.set_profile(LogicalProfile.TURBO, is_ac_online=True)
    assert res_turbo.success is True
    assert profile_manager.get_current_profile() == LogicalProfile.TURBO

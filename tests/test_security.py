"""Security tests for SCTRL.

Verifies:
1. Path traversal and symlink escape rejection in model profile loading.
2. Unknown model tier results in zero driver-specific hardware writes.
3. Imported/untrusted config cannot enable opt-ins automatically.
4. CapabilityRegistry tier check cannot be bypassed by any backend or manager.
5. Invalid fan values and malformed curves never reach the hardware backends.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from sctrl.errors import TierBlockedError, ValidationError
from sctrl.models import (
    CapabilityRecord,
    DMIInfo,
    FanCurve,
    FanCurvePoint,
    FeatureId,
    FeatureStatus,
    LogicalProfile,
    SupportTier,
)
from sctrl.model_db import ModelDatabase, load_profile_from_path
from daemon.capability_registry import CapabilityRegistry
from daemon.config_store import ConfigStore, DaemonConfig
from daemon.control.fan_control import FanControlManager
from daemon.control.profile_control import ProfileManager
from daemon.hardware.mock import MockConfig, MockHardwareManager, MockModel
from daemon.service import SCTRLService


def test_path_traversal_and_symlink_escape(tmp_path: Path) -> None:
    models_dir = tmp_path / "models_db"
    models_dir.mkdir()

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.toml"
    secret_file.write_text("""
[identity]
product_names = ["EVIL_MODEL"]
vendor = "Malicious"

[drivers]
primary = "acer-wmi"

[verification]
tester = "attacker"
date = "2024-01-01"
kernel_version = "6.8.0"
bios_version = "V1.00"
features_verified = ["fan_mode"]
""")

    # Create a symlink inside models_dir pointing to secret_file outside
    symlink_file = models_dir / "escaped.toml"
    try:
        os.symlink(str(secret_file), str(symlink_file))
        has_symlinks = True
    except (OSError, NotImplementedError):
        has_symlinks = False

    if has_symlinks:
        db = ModelDatabase(models_dir)
        # Escaped symlink must NOT be loaded
        profile = db.find_profile(DMIInfo(product_name="EVIL_MODEL"))
        assert profile is None, "Security vulnerability: Model database loaded a symlink escaping models_db"
        assert any("symlink escape" in err.lower() for err in db.load_errors)


def test_unknown_model_issues_zero_driver_writes(tmp_path: Path) -> None:
    # Service with an unknown/unsupported model (e.g., ThinkPad)
    cfg_file = tmp_path / "test_unsupported.toml"
    service = SCTRLService(
        mock_mode=True,
        mock_model="unsupported",
        config_path=cfg_file,
    )

    state = service.get_state()
    assert state.tier == SupportTier.UNSUPPORTED

    # Attempt driver-specific writes -> must be blocked
    with pytest.raises(TierBlockedError):
        service.set_fan_mode("max")

    with pytest.raises(TierBlockedError):
        service.set_profile("turbo")

    with pytest.raises(TierBlockedError):
        service.set_charge_limit(80)

    # Verify backend received no writes
    assert service._fans.get_current_mode().value == "auto"


def test_imported_config_cannot_enable_optins(tmp_path: Path) -> None:
    # A config trying to enable optin_experimental
    cfg_file = tmp_path / "malicious_config.toml"
    cfg_file.write_text("""
optin_experimental = true
default_profile = "performance"
""")

    # Boot service on DETECTED hardware
    service = SCTRLService(
        mock_mode=True,
        mock_model="detected",
        config_path=cfg_file,
    )

    # Opt-in must remain FALSE by default despite imported config setting
    assert service.registry.optins.get("performance_profile", False) is False

    # Attempting to write must fail until explicit runtime opt-in is granted
    with pytest.raises(TierBlockedError):
        service.set_profile("performance")

    # Now explicitly opt-in at runtime
    service.set_feature_optin("performance_profile", True)
    assert service.registry.optins["performance_profile"] is True

    # Now write is permitted
    res = service.set_profile("performance")
    assert res["success"] is True


def test_tier_check_cannot_be_bypassed() -> None:
    hw = MockHardwareManager(MockConfig(model=MockModel.UNSUPPORTED))
    reg = CapabilityRegistry()
    reg.set_tier(SupportTier.UNSUPPORTED, "Unsupported hardware")

    # Register fan mode capability
    reg.update_capabilities({
        FeatureId.FAN_MODE: CapabilityRecord(
            feature_id=FeatureId.FAN_MODE,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            tier=SupportTier.UNSUPPORTED,
        ),
        FeatureId.PERFORMANCE_PROFILE: CapabilityRecord(
            feature_id=FeatureId.PERFORMANCE_PROFILE,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            tier=SupportTier.UNSUPPORTED,
        ),
    })

    fan_mgr = FanControlManager(backend=hw.fan, registry=reg)
    prof_mgr = ProfileManager(backend=hw.profile, registry=reg)

    # Bypassing service and calling managers directly must STILL be blocked by registry check
    with pytest.raises(TierBlockedError):
        fan_mgr.set_mode_max("attacker")

    with pytest.raises(TierBlockedError):
        prof_mgr.set_profile(LogicalProfile.TURBO)


def test_invalid_fan_values_never_reach_backend() -> None:
    hw = MockHardwareManager(MockConfig(model=MockModel.VERIFIED))
    reg = CapabilityRegistry()
    reg.set_tier(SupportTier.VERIFIED, "Verified")
    reg.update_capabilities({
        FeatureId.FAN_CURVE: CapabilityRecord(
            feature_id=FeatureId.FAN_CURVE,
            status=FeatureStatus.SUPPORTED,
            writable=True,
            tier=SupportTier.VERIFIED,
        ),
    })

    fan_mgr = FanControlManager(backend=hw.fan, registry=reg)

    # 1. Invalid speed > 100%
    invalid_curve_high = FanCurve(
        points=[FanCurvePoint(40, 20), FanCurvePoint(70, 150)]
    )
    with pytest.raises(ValidationError):
        fan_mgr.set_custom_curve("user", cpu_curve=invalid_curve_high)

    # 2. Negative speed
    invalid_curve_neg = FanCurve(
        points=[FanCurvePoint(40, -10), FanCurvePoint(70, 50)]
    )
    with pytest.raises(ValidationError):
        fan_mgr.set_custom_curve("user", cpu_curve=invalid_curve_neg)

    # 3. Non-monotonic speed (decreasing fan speed at higher temperature)
    invalid_curve_non_monotonic = FanCurve(
        points=[FanCurvePoint(40, 80), FanCurvePoint(70, 20)]
    )
    with pytest.raises(ValidationError):
        fan_mgr.set_custom_curve("user", cpu_curve=invalid_curve_non_monotonic)

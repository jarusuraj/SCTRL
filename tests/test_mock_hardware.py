"""Unit tests for daemon.hardware.mock."""

from __future__ import annotations

import pytest
from sctrl.models import SupportTier, ValueQuality
from daemon.hardware.mock import MockConfig, MockHardwareManager, MockModel


def test_mock_tiers() -> None:
    for model_tier in [MockModel.VERIFIED, MockModel.COMMUNITY, MockModel.DETECTED, MockModel.UNSUPPORTED, MockModel.BIOS_MISMATCH]:
        mgr = MockHardwareManager(MockConfig(model=model_tier))
        dmi = mgr.system_info.read_dmi()
        assert dmi.product_name != ""

        # Read sensors
        cpu_t = mgr.sensor.read_cpu_temp()
        assert cpu_t.is_available is True
        assert cpu_t.value is not None


def test_mock_gpu_suspended() -> None:
    # When GPU is suspended, read_gpu_temp must return UNAVAILABLE without waking GPU
    cfg = MockConfig(model=MockModel.VERIFIED, gpu_suspended=True)
    mgr = MockHardwareManager(cfg)
    assert mgr.system_info.is_gpu_suspended() is True

    gpu_t = mgr.sensor.read_gpu_temp()
    assert gpu_t.quality == ValueQuality.UNAVAILABLE
    assert gpu_t.value is None


def test_mock_failure_simulation() -> None:
    cfg = MockConfig(model=MockModel.VERIFIED, simulate_permission_denied=True)
    mgr = MockHardwareManager(cfg)

    # Writes should fail with permission error
    res = mgr.fan.set_mode_max()
    assert res.success is False
    assert "permission" in res.error.lower()

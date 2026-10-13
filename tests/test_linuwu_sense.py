"""Unit tests for daemon.hardware.linuwu_sense and discovery mode."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
import pytest

from sctrl.models import FanMode, FeatureId, FeatureStatus
from sctrl.model_db import ModelProfile, FanProfile
from daemon.hardware.linuwu_sense import LinuwuSenseBackend
from sctrl.cli import main


def test_linuwu_sense_exact_node_resolution(tmp_path: Path) -> None:
    """Nodes must only be resolved from exact names listed in model profile quirks (verified in docs/hw-dump.txt)."""
    driver_dir = tmp_path / "linuwu-sense"
    driver_dir.mkdir()

    mode_file = driver_dir / "fan_mode"
    mode_file.write_text("auto")

    cpu_speed_file = driver_dir / "cpu_fan_speed"
    cpu_speed_file.write_text("50")

    gpu_speed_file = driver_dir / "gpu_fan_speed"
    gpu_speed_file.write_text("50")

    profile_file = driver_dir / "platform_profile"
    profile_file.write_text("balanced")

    # Profile with exact quirks matching docs/hw-dump.txt
    profile = ModelProfile(
        product_names=["PHN16-72"],
        vendor="Acer",
        fans=FanProfile(count=2, max_speed_percent=100),
        quirks={

            "linuwu_base_dir": str(driver_dir),
            "linuwu_fan_mode_node": "fan_mode",
            "linuwu_cpu_speed_node": "cpu_fan_speed",
            "linuwu_gpu_speed_node": "gpu_fan_speed",
            "linuwu_profile_node": "platform_profile",
        },
    )

    backend = LinuwuSenseBackend(base_dir=driver_dir, model_profile=profile)
    assert backend.is_available is True

    caps = backend.probe()
    cap_map = {c.feature_id: c for c in caps}

    assert cap_map[FeatureId.FAN_MODE].status == FeatureStatus.SUPPORTED
    assert cap_map[FeatureId.FAN_CURVE].status == FeatureStatus.SUPPORTED
    assert cap_map[FeatureId.PERFORMANCE_PROFILE].status == FeatureStatus.SUPPORTED

    # Write test
    res = backend.set_mode_max()
    assert res.success is True
    assert mode_file.read_text().strip() == "max"

    res_speed = backend.set_fan_speed("cpu", 85)
    assert res_speed.success is True
    assert cpu_speed_file.read_text().strip() == "85"


def test_linuwu_sense_unknown_node_results_in_driver_missing_and_no_write(tmp_path: Path) -> None:
    """Unknown or unconfigured nodes result in DRIVER_MISSING and zero write."""
    driver_dir = tmp_path / "linuwu-sense"
    driver_dir.mkdir()

    # Even if files exist with random names, without exact quirks match they must NOT be used
    fuzzy_mode_file = driver_dir / "predator_fan_mode_node"
    fuzzy_mode_file.write_text("auto")

    # Empty profile (no quirks)
    empty_profile = ModelProfile(
        product_names=["UnknownModel"],
        vendor="Acer",
        quirks={},
    )

    backend = LinuwuSenseBackend(base_dir=driver_dir, model_profile=empty_profile)
    caps = backend.probe()
    cap_map = {c.feature_id: c for c in caps}

    assert cap_map[FeatureId.FAN_MODE].status == FeatureStatus.DRIVER_MISSING
    assert cap_map[FeatureId.FAN_CURVE].status == FeatureStatus.DRIVER_MISSING
    assert cap_map[FeatureId.PERFORMANCE_PROFILE].status == FeatureStatus.DRIVER_MISSING

    # Attempting write must return success=False and not write to any file
    res = backend.set_mode_max()
    assert res.success is False
    assert res.error != ""
    assert fuzzy_mode_file.read_text().strip() == "auto"


def test_cli_discover_mode(capsys: pytest.CaptureFixture[str]) -> None:
    test_args = ["sctrl", "--mock", "--discover"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "=== SCTRL Read-Only Hardware Discovery ===" in captured.out
    assert "Capabilities Discovered:" in captured.out
    assert "fan_mode" in captured.out

"""Unit tests for daemon.hardware.linuwu_sense and discovery mode."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch
import pytest

from sctrl.models import FanMode, FeatureId, FeatureStatus
from daemon.hardware.linuwu_sense import LinuwuSenseBackend
from sctrl.cli import main


def test_linuwu_sense_dynamic_discovery(tmp_path: Path) -> None:
    # Create simulated sysfs tree for linuwu-sense
    driver_dir = tmp_path / "linuwu-sense"
    driver_dir.mkdir()

    # Dynamically named nodes
    mode_file = driver_dir / "fan_mode"
    mode_file.write_text("auto")

    cpu_speed_file = driver_dir / "cpu_fan_speed"
    cpu_speed_file.write_text("50")

    gpu_speed_file = driver_dir / "gpu_fan_speed"
    gpu_speed_file.write_text("50")

    backend = LinuwuSenseBackend(base_dir=driver_dir)
    assert backend.is_available is True

    caps = backend.probe()
    cap_ids = [c.feature_id for c in caps]
    assert FeatureId.FAN_MODE in cap_ids
    assert FeatureId.FAN_CURVE in cap_ids

    # Write test
    res = backend.set_mode_max()
    assert res.success is True
    assert mode_file.read_text().strip() == "max"

    res_speed = backend.set_fan_speed("cpu", 85)
    assert res_speed.success is True
    assert cpu_speed_file.read_text().strip() == "85"


def test_cli_discover_mode(capsys: pytest.CaptureFixture[str]) -> None:
    test_args = ["sctrl", "--mock", "--discover"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "=== SCTRL Read-Only Hardware Discovery ===" in captured.out
    assert "Capabilities Discovered:" in captured.out
    assert "fan_mode" in captured.out

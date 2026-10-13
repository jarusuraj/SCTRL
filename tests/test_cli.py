"""Tests for SCTRL CLI interface."""

from __future__ import annotations

import sys
from io import StringIO
from unittest.mock import patch
import pytest
from sctrl.cli import main


def test_cli_mock_status(capsys: pytest.CaptureFixture[str]) -> None:
    test_args = ["sctrl", "--mock", "status"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "=== SCTRL v0.1.0 Status ===" in captured.out
    assert "Support Tier:" in captured.out
    assert "CPU Temp:" in captured.out


def test_cli_mock_fan(capsys: pytest.CaptureFixture[str]) -> None:
    test_args = ["sctrl", "--mock", "fan", "max"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "Fan mode set to max" in captured.out


def test_cli_mock_profile(capsys: pytest.CaptureFixture[str]) -> None:
    test_args = ["sctrl", "--mock", "profile", "turbo"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert "Profile set to turbo" in captured.out


def test_cli_mock_diagnostics(capsys: pytest.CaptureFixture[str]) -> None:
    test_args = ["sctrl", "--mock", "diagnostics"]
    with patch.object(sys, "argv", test_args):
        main()

    captured = capsys.readouterr()
    assert '"tier":' in captured.out
    assert '"capabilities":' in captured.out


def test_cli_report_model(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out_file = tmp_path / "model_report.json"
    test_args = ["sctrl", "--mock", "report-model", "--output", str(out_file)]
    with patch.object(sys, "argv", test_args):
        main()

    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert '"report_type": "sctrl_hardware_model_report"' in content
    assert '"serial_number": "[REDACTED]"' in content
    assert '"uuid": "[REDACTED]"' in content


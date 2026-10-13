"""Integration tests for SCTRLService and end-to-end workflows."""

from __future__ import annotations

from pathlib import Path
import pytest
from sctrl.constants import MODELS_DB_DIR
from sctrl.models import FanMode, LogicalProfile, SupportTier
from daemon.service import SCTRLService


def test_service_lifecycle_and_state(tmp_path: Path) -> None:
    cfg_file = tmp_path / "test_sctrl.toml"
    service = SCTRLService(
        mock_mode=True,
        mock_model="verified",
        config_path=cfg_file,
        models_dir=MODELS_DB_DIR,
    )

    # 1. Inspect state
    state = service.get_state()
    assert state.mock_mode is True
    assert state.tier == SupportTier.COMMUNITY  # PHN16-72 is in models_db without physical verification evidence
    assert state.fan_mode == FanMode.AUTO

    # 2. Tick telemetry
    snapshot = service.tick()
    assert snapshot.cpu_temp.is_available is True
    assert snapshot.cpu_temp.value is not None
    assert snapshot.battery_percent.value is not None

    # 3. Fan control
    res_fan = service.set_fan_mode("max")
    assert res_fan["success"] is True
    state_after = service.get_state()
    assert state_after.fan_mode == FanMode.MAX
    assert state_after.fan_lease_active is True

    # 4. Profile control
    res_prof = service.set_profile("performance")
    assert res_prof["success"] is True

    # 5. Battery limit
    res_bat = service.set_charge_limit(80)
    assert res_bat["success"] is True

    # 6. Diagnostics
    diag = service.get_diagnostics()
    assert diag.dmi.product_name != ""
    assert len(diag.capabilities) > 0

    # 7. Clean stop
    service.stop()

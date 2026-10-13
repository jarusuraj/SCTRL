"""Unit tests for daemon.config_store."""

from __future__ import annotations

from pathlib import Path
import pytest
from daemon.config_store import ConfigStore, DaemonConfig


def test_config_store_save_load(tmp_path: Path) -> None:
    cfg_path = tmp_path / "sctrl.toml"
    store = ConfigStore(cfg_path)

    # Initial load -> defaults
    cfg = store.load()
    assert cfg.charge_limit_percent == 80
    assert cfg.default_profile == "balanced"

    # Modify and save
    cfg.charge_limit_percent = 70
    cfg.default_profile = "performance"
    store.save(cfg)

    assert cfg_path.exists()

    # Load in new store
    new_store = ConfigStore(cfg_path)
    loaded = new_store.load()
    assert loaded.charge_limit_percent == 70
    assert loaded.default_profile == "performance"


def test_config_store_backup_recovery(tmp_path: Path) -> None:
    cfg_path = tmp_path / "sctrl.toml"
    store = ConfigStore(cfg_path)

    cfg = store.load()
    cfg.charge_limit_percent = 65
    store.save(cfg)

    # Corrupt main file
    with open(cfg_path, "w") as f:
        f.write("corrupted = [invalid toml syntax")

    # Load should safely recover from backup or defaults without crashing
    recovered_store = ConfigStore(cfg_path)
    recovered = recovered_store.load()
    assert isinstance(recovered, DaemonConfig)

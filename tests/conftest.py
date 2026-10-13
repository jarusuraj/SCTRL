"""Test suite configuration and shared fixtures for SCTRL."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

# Ensure src and root are in sys.path
root_dir = Path(__file__).parent.parent
src_dir = root_dir / "src"

if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from sctrl.constants import MODELS_DB_DIR
from sctrl.model_db import ModelDatabase
from daemon.capability_registry import CapabilityRegistry
from daemon.hardware.mock import MockConfig, MockHardwareManager, MockModel
from daemon.service import SCTRLService


@pytest.fixture
def model_db() -> ModelDatabase:
    return ModelDatabase(MODELS_DB_DIR)


@pytest.fixture
def mock_hw_verified() -> MockHardwareManager:
    return MockHardwareManager(MockConfig(model=MockModel.VERIFIED))


@pytest.fixture
def mock_hw_community() -> MockHardwareManager:
    return MockHardwareManager(MockConfig(model=MockModel.COMMUNITY))


@pytest.fixture
def mock_hw_detected() -> MockHardwareManager:
    return MockHardwareManager(MockConfig(model=MockModel.DETECTED))


@pytest.fixture
def mock_hw_unsupported() -> MockHardwareManager:
    return MockHardwareManager(MockConfig(model=MockModel.UNSUPPORTED))


@pytest.fixture
def mock_service_verified(tmp_path: Path) -> SCTRLService:
    cfg_file = tmp_path / "test_config.toml"
    service = SCTRLService(
        mock_mode=True,
        mock_model="verified",
        config_path=cfg_file,
        models_dir=MODELS_DB_DIR,
    )
    return service

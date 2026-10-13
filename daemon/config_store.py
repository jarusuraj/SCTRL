"""Persistent configuration store for SCTRL daemon.

Provides atomic file writes, automatic backup, and schema-validated persistence
for user preferences (fan curves, charge limits, performance profiles, RGB).
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sctrl.constants import (
    CONFIG_FILE,
    DEFAULT_CHARGE_LIMIT_PCT,
    DEFAULT_KEYBOARD_BRIGHTNESS,
    FAN_LEASE_DEFAULT_S,
    TELEMETRY_POLL_INTERVAL_S,
)
from sctrl.errors import ConfigError

logger = logging.getLogger("sctrld.config_store")


@dataclass
class DaemonConfig:
    """Daemon configuration schema."""
    # Profiles & Fans
    default_profile: str = "balanced"
    fan_mode: str = "auto"
    custom_cpu_curve: list[dict[str, int]] = field(default_factory=list)
    custom_gpu_curve: list[dict[str, int]] = field(default_factory=list)

    # Battery
    charge_limit_percent: int = DEFAULT_CHARGE_LIMIT_PCT
    charge_limit_enabled: bool = False

    # Keyboard Backlight & RGB
    keyboard_brightness: int = DEFAULT_KEYBOARD_BRIGHTNESS
    keyboard_effect: str = "static"
    keyboard_speed: int = 50
    zone_colors: list[list[int]] = field(
        default_factory=lambda: [[0, 120, 255], [0, 120, 255], [0, 120, 255], [0, 120, 255]]
    )

    # Safety & Timing
    telemetry_poll_interval_s: float = TELEMETRY_POLL_INTERVAL_S
    fan_lease_duration_s: int = FAN_LEASE_DEFAULT_S
    thermal_override_enabled: bool = True
    cpu_warn_temp_c: int = 85
    cpu_critical_temp_c: int = 95
    gpu_warn_temp_c: int = 80
    gpu_critical_temp_c: int = 88

    # Model & Opt-in
    optin_experimental: bool = False
    mock_mode: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DaemonConfig:
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class ConfigStore:
    """Manages loading, saving, and atomic persistence of daemon config."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path:
            self._path = Path(config_path)
        else:
            self._path = CONFIG_FILE
        self._config = DaemonConfig()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def config(self) -> DaemonConfig:
        return self._config

    def load(self) -> DaemonConfig:
        """Load configuration from file. Falls back to backup or defaults on error."""
        if not self._path.exists():
            logger.info("Config file %s does not exist, using defaults", self._path)
            self._config = DaemonConfig()
            return self._config

        try:
            with open(self._path, "rb") as f:
                data = tomllib.load(f)
            self._config = DaemonConfig.from_dict(data)
            logger.info("Loaded config from %s", self._path)
            return self._config
        except Exception as e:
            logger.warning("Failed to parse config %s: %s. Attempting backup restore...", self._path, e)
            bak_path = self._path.with_suffix(".toml.bak")
            if bak_path.exists():
                try:
                    with open(bak_path, "rb") as f:
                        data = tomllib.load(f)
                    self._config = DaemonConfig.from_dict(data)
                    logger.info("Restored config from backup %s", bak_path)
                    return self._config
                except Exception as bak_err:
                    logger.error("Failed to parse backup %s: %s", bak_path, bak_err)

            logger.warning("Using default configuration due to errors")
            self._config = DaemonConfig()
            return self._config

    def save(self, config: DaemonConfig | None = None) -> None:
        """Atomically save configuration to disk with backup."""
        if config is not None:
            self._config = config

        data = self._config.to_dict()
        toml_content = self._serialize_toml(data)

        # Ensure directory exists
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write: write to temp file in the same directory, then rename
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=f"{self._path.stem}_",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_path_str)

        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                f.write(toml_content)
                f.flush()
                os.fsync(f.fileno())

            # Create backup if original exists
            if self._path.exists():
                bak_path = self._path.with_suffix(".toml.bak")
                try:
                    shutil.copy2(self._path, bak_path)
                except Exception as e:
                    logger.warning("Failed to create config backup: %s", e)

            # Atomic replace
            os.replace(tmp_path, self._path)
            logger.info("Atomically saved configuration to %s", self._path)
        except Exception as e:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            raise ConfigError(f"Failed to atomically write config: {e}") from e

    def _serialize_toml(self, data: dict[str, Any]) -> str:
        """Simple, deterministic TOML serializer for daemon config."""
        lines = [
            "# SCTRL Daemon Configuration File",
            "# Automatically managed by sctrld. Do not edit while daemon is running.",
            "",
        ]

        # Top-level primitives
        for k, v in data.items():
            if isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, (int, float)):
                lines.append(f"{k} = {v}")
            elif isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, list):
                # Format list
                if not v:
                    lines.append(f"{k} = []")
                elif all(isinstance(x, (int, float, str, list)) for x in v):
                    formatted_items = []
                    for item in v:
                        if isinstance(item, list):
                            formatted_items.append("[" + ", ".join(str(sub) for sub in item) + "]")
                        elif isinstance(item, str):
                            formatted_items.append(f'"{item}"')
                        else:
                            formatted_items.append(str(item))
                    lines.append(f"{k} = [{', '.join(formatted_items)}]")
                elif all(isinstance(x, dict) for x in v):
                    # Array of tables or inline dicts
                    lines.append(f"# Array for {k}")
                    for idx, item in enumerate(v):
                        lines.append(f"[[{k}]]")
                        for sub_k, sub_v in item.items():
                            if isinstance(sub_v, str):
                                lines.append(f'  {sub_k} = "{sub_v}"')
                            else:
                                lines.append(f"  {sub_k} = {sub_v}")
            lines.append("")

        return "\n".join(lines)

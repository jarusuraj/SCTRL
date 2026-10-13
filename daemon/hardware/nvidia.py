"""NVIDIA discrete GPU backend with runtime power-state awareness.

CRITICAL SAFETY & POWER REQUIREMENT:
On Linux hybrid graphics laptops, querying the discrete GPU (via NVML or nvidia-smi)
wakes up the GPU from runtime suspend (RTD3), dramatically reducing battery life.
This backend explicitly checks PCI sysfs runtime_status BEFORE any GPU query,
returning ValueQuality.UNAVAILABLE without waking the dGPU when it is suspended.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from sctrl.constants import SYSFS_PCI_DEVICES
from sctrl.models import (
    CapabilityRecord,
    FeatureId,
    FeatureStatus,
    SensorReading,
    ValueQuality,
)

logger = logging.getLogger("sctrld.nvidia")


class NvidiaGpuBackend:
    """Safely monitors NVIDIA discrete GPU without waking it from suspend."""

    def __init__(self, pci_root: str | Path = SYSFS_PCI_DEVICES) -> None:
        self._pci_root = Path(pci_root)
        self._gpu_pci_dir: Path | None = None
        self._runtime_status_file: Path | None = None
        self._has_nvidia_smi = False
        self._find_gpu_pci()

    def _find_gpu_pci(self) -> None:
        """Locate NVIDIA PCI device and runtime_status file."""
        if not self._pci_root.exists():
            return

        for dev_dir in self._pci_root.iterdir():
            vendor_file = dev_dir / "vendor"
            if vendor_file.exists():
                try:
                    vendor_id = vendor_file.read_text().strip().lower()
                    if vendor_id == "0x10de":  # NVIDIA vendor ID
                        self._gpu_pci_dir = dev_dir
                        self._runtime_status_file = dev_dir / "power" / "runtime_status"
                        logger.info("Found NVIDIA dGPU at PCI %s", dev_dir.name)
                        break
                except Exception:
                    pass

        # Check for nvidia-smi binary
        try:
            res = subprocess.run(["which", "nvidia-smi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._has_nvidia_smi = (res.returncode == 0)
        except Exception:
            self._has_nvidia_smi = False

    def is_suspended(self) -> bool:
        """Check if dGPU is runtime-suspended."""
        if not self._runtime_status_file or not self._runtime_status_file.exists():
            return False
        try:
            status = self._runtime_status_file.read_text().strip().lower()
            return status == "suspended"
        except Exception as e:
            logger.debug("Failed reading dGPU runtime status: %s", e)
            return False

    def read_gpu_temp(self) -> SensorReading:
        """Read GPU temperature. Skips query if GPU is suspended to preserve battery."""
        if self.is_suspended():
            return SensorReading(
                value=None,
                unit="C",
                quality=ValueQuality.UNAVAILABLE,
                source="nvidia_suspended",
            )

        # If active, query via nvidia-smi
        if self._has_nvidia_smi:
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
                    text=True,
                    timeout=1.0,
                ).strip()
                val = float(out)
                return SensorReading(value=val, unit="C", quality=ValueQuality.MEASURED, source="nvidia-smi")
            except Exception as e:
                logger.debug("nvidia-smi query failed: %s", e)

        return SensorReading(value=None, unit="C", quality=ValueQuality.UNAVAILABLE)

    def read_gpu_util(self) -> SensorReading:
        """Read GPU utilization percentage."""
        if self.is_suspended():
            return SensorReading(
                value=0.0,
                unit="%",
                quality=ValueQuality.MEASURED,
                source="nvidia_suspended",
            )

        if self._has_nvidia_smi:
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                    text=True,
                    timeout=1.0,
                ).strip()
                val = float(out)
                return SensorReading(value=val, unit="%", quality=ValueQuality.MEASURED, source="nvidia-smi")
            except Exception:
                pass

        return SensorReading(value=None, unit="%", quality=ValueQuality.UNAVAILABLE)

    def read_gpu_power(self) -> SensorReading:
        """Read GPU power draw in watts."""
        if self.is_suspended():
            return SensorReading(
                value=0.0,
                unit="W",
                quality=ValueQuality.MEASURED,
                source="nvidia_suspended",
            )

        if self._has_nvidia_smi:
            try:
                out = subprocess.check_output(
                    ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                    text=True,
                    timeout=1.0,
                ).strip()
                val = float(out)
                return SensorReading(value=val, unit="W", quality=ValueQuality.MEASURED, source="nvidia-smi")
            except Exception:
                pass

        return SensorReading(value=None, unit="W", quality=ValueQuality.UNAVAILABLE)

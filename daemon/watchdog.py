"""Watchdog and telemetry polling loop for SCTRL daemon.

Responsible for:
- Periodic hardware telemetry sampling
- Fan lease expiration enforcement (safety return to AUTO)
- Thermal threshold monitoring and emergency override execution
- Stale sensor detection
- Subscriber notification
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from sctrl.constants import TELEMETRY_POLL_INTERVAL_S
from sctrl.models import FanMode, SensorReading, TelemetrySnapshot, ValueQuality
from daemon.control.fan_control import FanControlManager
from daemon.control.thermal_policy import ThermalAlert, ThermalPolicy, ThermalState
from daemon.hardware.base import BatteryBackend, SensorBackend, SystemInfoBackend

logger = logging.getLogger("sctrld.watchdog")


class DaemonWatchdog:
    """Supervises hardware state, enforces lease timeouts and thermal safety."""

    def __init__(
        self,
        sensors: SensorBackend,
        system_info: SystemInfoBackend,
        battery: BatteryBackend,
        fan_manager: FanControlManager,
        thermal_policy: ThermalPolicy,
        poll_interval_s: float = TELEMETRY_POLL_INTERVAL_S,
        on_telemetry_updated: Callable[[TelemetrySnapshot], None] | None = None,
        on_thermal_alert: Callable[[ThermalAlert], None] | None = None,
    ) -> None:
        self._sensors = sensors
        self._system_info = system_info
        self._battery = battery
        self._fan_manager = fan_manager
        self._thermal_policy = thermal_policy
        self._poll_interval = poll_interval_s

        self._on_telemetry_updated = on_telemetry_updated
        self._on_thermal_alert = on_thermal_alert

        self._last_snapshot: TelemetrySnapshot = TelemetrySnapshot()
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Wire thermal policy emergency action to fan manager
        self._thermal_policy.set_emergency_callback(self._on_emergency_trigger)

    @property
    def latest_telemetry(self) -> TelemetrySnapshot:
        with self._lock:
            return self._last_snapshot

    def _on_emergency_trigger(self, is_emergency: bool) -> None:
        """Triggered when thermal policy enters or exits CRITICAL state."""
        if is_emergency:
            logger.critical("EMERGENCY THERMAL OVERRIDE TRIGGERED! Forcing safe fan mode.")
            self._fan_manager.trigger_emergency_override(reason="critical_temperature")
        else:
            logger.info("Thermal emergency cleared. Restoring normal fan operation.")
            self._fan_manager.clear_emergency_override()

    def tick(self) -> TelemetrySnapshot:
        """Execute a single polling and supervision cycle synchronously."""
        # 1. Check fan lease expiration
        self._fan_manager.check_lease_expiry()

        # 2. Sample hardware sensors
        cpu_temp = self._sensors.read_cpu_temp()
        gpu_temp = self._sensors.read_gpu_temp()
        cpu_rpm = self._sensors.read_cpu_fan_rpm()
        gpu_rpm = self._sensors.read_gpu_fan_rpm()
        cpu_power = self._sensors.read_cpu_power()
        gpu_power = self._sensors.read_gpu_power()

        cpu_util = self._system_info.read_cpu_util()
        ram_used, ram_total, ram_util = self._system_info.read_ram_usage()
        gpu_util = self._system_info.read_gpu_util()
        uptime = self._system_info.read_uptime()

        battery_pct = self._battery.read_charge_percent()
        battery_state = self._battery.read_charge_state()
        charge_limit_val = self._battery.get_charge_limit()
        charge_limit_reading = SensorReading(
            value=float(charge_limit_val) if charge_limit_val is not None else None,
            unit="%",
            quality=ValueQuality.MEASURED if charge_limit_val is not None else ValueQuality.UNAVAILABLE,
        )

        snapshot = TelemetrySnapshot(
            timestamp=time.time(),
            cpu_temp=cpu_temp,
            gpu_temp=gpu_temp,
            cpu_util=cpu_util,
            gpu_util=gpu_util,
            cpu_fan_rpm=cpu_rpm,
            gpu_fan_rpm=gpu_rpm,
            cpu_power=cpu_power,
            gpu_power=gpu_power,
            ram_used_bytes=ram_used,
            ram_total_bytes=ram_total,
            ram_util=ram_util,
            battery_percent=battery_pct,
            battery_state=battery_state,
            charge_limit=charge_limit_reading,
            uptime_seconds=uptime,
        )

        with self._lock:
            self._last_snapshot = snapshot

        # 3. Update fan curve controller if active lease
        if self._fan_manager.current_mode == FanMode.CUSTOM:
            self._fan_manager.apply_curve_tick(cpu_temp.value, gpu_temp.value)

        # 4. Check thermal policy
        alerts = self._thermal_policy.evaluate(cpu_temp, gpu_temp)
        for alert in alerts:
            if self._on_thermal_alert:
                self._on_thermal_alert(alert)

        # 5. Notify telemetry update callback
        if self._on_telemetry_updated:
            self._on_telemetry_updated(snapshot)

        return snapshot

    def start(self) -> None:
        """Start watchdog thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="sctrld-watchdog", daemon=True)
        self._thread.start()
        logger.info("Watchdog supervision loop started (interval=%.1fs)", self._poll_interval)

    def stop(self) -> None:
        """Stop watchdog thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Watchdog supervision loop stopped")

    def _loop(self) -> None:
        """Background loop."""
        while self._running:
            start_t = time.monotonic()
            try:
                self.tick()
            except Exception as e:
                logger.error("Error during watchdog tick: %s", e, exc_info=True)

            elapsed = time.monotonic() - start_t
            sleep_t = max(0.05, self._poll_interval - elapsed)
            time.sleep(sleep_t)

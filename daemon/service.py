"""Core SCTRL daemon service orchestrator.

Integrates hardware backends, model database, capability registry, control
managers, thermal watchdog, and configuration persistence into a unified engine.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from sctrl.constants import (
    DEFAULT_CHARGE_LIMIT_PCT,
    DEFAULT_KEYBOARD_BRIGHTNESS,
    MODELS_DB_DIR,
)
from sctrl.errors import SCTRLError, UnsupportedError, ValidationError
from sctrl.model_db import ModelDatabase
from sctrl.models import (
    CapabilityRecord,
    DaemonState,
    DiagnosticReport,
    DMIInfo,
    FanCurve,
    FanMode,
    FeatureId,
    KeyboardEffect,
    LogicalProfile,
    ProfileState,
    RGBColor,
    SensorReading,
    SupportTier,
    TelemetrySnapshot,
)
from daemon.capability_registry import CapabilityRegistry
from daemon.config_store import ConfigStore, DaemonConfig
from daemon.control.battery_control import BatteryController
from daemon.control.fan_control import FanControlManager
from daemon.control.keyboard_control import KeyboardController
from daemon.control.profile_control import ProfileManager
from daemon.control.thermal_policy import ThermalAlert, ThermalPolicy, ThermalThresholds
from daemon.hardware.discovery import DiscoveryResult, HardwareDiscovery
from daemon.hardware.mock import MockConfig, MockHardwareManager, MockModel
from daemon.watchdog import DaemonWatchdog

logger = logging.getLogger("sctrld.service")


class SCTRLService:
    """The central SCTRL daemon service."""

    def __init__(
        self,
        mock_mode: bool = False,
        mock_model: str = "verified",
        config_path: Path | str | None = None,
        models_dir: Path | str | None = None,
        poll_interval_s: float = 1.0,
        read_only_discovery: bool = False,
    ) -> None:
        self._mock_mode = mock_mode
        self._mock_model_str = mock_model
        self._models_dir = Path(models_dir) if models_dir else MODELS_DB_DIR
        self._config_store = ConfigStore(config_path)
        self._registry = CapabilityRegistry()
        self._model_db = ModelDatabase(self._models_dir)
        self._poll_interval = poll_interval_s
        self._read_only_discovery = read_only_discovery

        self._recent_errors: list[str] = []
        self._telemetry_subscribers: list[Callable[[TelemetrySnapshot], None]] = []
        self._alert_subscribers: list[Callable[[ThermalAlert], None]] = []

        self._init_hardware_and_managers()

    def _init_hardware_and_managers(self) -> None:
        """Initialize hardware backends, discovery, and managers."""
        # 1. Load config
        self._config = self._config_store.load()

        # 2. Select backends (mock vs real)
        if self._mock_mode:
            logger.info("Initializing in MOCK mode with model preset '%s'", self._mock_model_str)
            try:
                preset = MockModel(self._mock_model_str)
            except ValueError:
                preset = MockModel.VERIFIED
            mock_cfg = MockConfig(model=preset)
            self._mock_mgr = MockHardwareManager(mock_cfg)

            self._sensors = self._mock_mgr.sensor
            self._fans = self._mock_mgr.fan
            self._profiles = self._mock_mgr.profile
            self._battery = self._mock_mgr.battery
            self._keyboard = self._mock_mgr.keyboard
            self._sys_info = self._mock_mgr.system_info
        else:
            logger.info("Initializing in REAL hardware mode")
            from daemon.hardware.acer_wmi import AcerWmiFanBackend, PlatformProfileBackend
            from daemon.hardware.battery import SysfsBatteryBackend
            from daemon.hardware.hwmon import HwmonSensorBackend
            from daemon.hardware.rgb import AcerKeyboardBackend
            from daemon.hardware.system_info import RealSystemInfoBackend

            self._sensors = HwmonSensorBackend()
            self._fans = AcerWmiFanBackend()
            self._profiles = PlatformProfileBackend()
            self._battery = SysfsBatteryBackend()
            self._keyboard = AcerKeyboardBackend()
            self._sys_info = RealSystemInfoBackend()

        # 3. Run discovery
        discovery = HardwareDiscovery(
            model_db=self._model_db,
            system_info=self._sys_info,
            sensor=self._sensors,
            fan_control=self._fans,
            profile=self._profiles,
            battery=self._battery,
            keyboard=self._keyboard,
        )
        self._discovery_result = discovery.discover()

        # 4. Populate registry
        self._registry.update_capabilities(self._discovery_result.capabilities)
        self._registry.set_tier(
            self._discovery_result.tier_result.tier,
            self._discovery_result.tier_result.reason,
        )

        # Apply persisted opt-ins
        if self._config.optin_experimental:
            for feat_name in ("performance_profile", "charge_limit"):
                self._registry.set_optin(feat_name, True)

        # 5. Model profile mapping for performance profiles
        model_mapping = None
        if self._discovery_result.profile and hasattr(self._discovery_result.profile, "profile_mapping"):
            model_mapping = self._discovery_result.profile.profile_mapping

        # 6. Instantiate managers
        self._fan_mgr = FanControlManager(self._fans, self._registry)
        self._profile_mgr = ProfileManager(self._profiles, self._registry, model_mapping)
        self._battery_mgr = BatteryController(self._battery, self._registry)
        self._keyboard_mgr = KeyboardController(self._keyboard, self._registry)

        # 7. Thermal policy
        thresholds = ThermalThresholds(
            cpu_warn_c=self._config.cpu_warn_temp_c,
            cpu_critical_c=self._config.cpu_critical_temp_c,
            gpu_warn_c=self._config.gpu_warn_temp_c,
            gpu_critical_c=self._config.gpu_critical_temp_c,
        )
        self._thermal_policy = ThermalPolicy(thresholds=thresholds)

        # 8. Watchdog
        self._watchdog = DaemonWatchdog(
            sensors=self._sensors,
            system_info=self._sys_info,
            battery=self._battery,
            fan_manager=self._fan_mgr,
            thermal_policy=self._thermal_policy,
            poll_interval_s=self._poll_interval,
            on_telemetry_updated=self._dispatch_telemetry,
            on_thermal_alert=self._dispatch_alert,
        )

        # 9. Apply initial configuration safely (skip in read-only discovery mode)
        if not self._read_only_discovery:
            self._apply_initial_config()

    def _apply_initial_config(self) -> None:
        """Apply stored user preferences respecting tier permissions."""
        logger.info("Applying initial configuration...")

        # Battery limit
        if self._config.charge_limit_enabled and self._battery_mgr.is_charge_limit_supported:
            try:
                if self._registry.is_feature_writable(FeatureId.CHARGE_LIMIT):
                    self._battery_mgr.set_charge_limit(self._config.charge_limit_percent)
            except Exception as e:
                logger.warning("Could not apply initial charge limit: %s", e)

        # Profile
        if self._profile_mgr.is_supported:
            try:
                target_lp = LogicalProfile(self._config.default_profile)
                if self._registry.is_feature_writable(FeatureId.PERFORMANCE_PROFILE):
                    self._profile_mgr.set_profile(target_lp)
            except Exception as e:
                logger.warning("Could not apply initial profile: %s", e)

        # Keyboard brightness
        if self._keyboard_mgr.is_brightness_supported:
            try:
                if self._registry.is_feature_writable(FeatureId.KEYBOARD_BRIGHTNESS):
                    self._keyboard_mgr.set_brightness(self._config.keyboard_brightness)
            except Exception as e:
                logger.warning("Could not apply initial keyboard brightness: %s", e)

    def _dispatch_telemetry(self, snapshot: TelemetrySnapshot) -> None:
        for sub in self._telemetry_subscribers:
            try:
                sub(snapshot)
            except Exception as e:
                logger.debug("Error in telemetry subscriber: %s", e)

    def _dispatch_alert(self, alert: ThermalAlert) -> None:
        for sub in self._alert_subscribers:
            try:
                sub(alert)
            except Exception as e:
                logger.debug("Error in alert subscriber: %s", e)

    def start(self) -> None:
        """Start watchdog supervision loop."""
        self._watchdog.start()

    def stop(self) -> None:
        """Stop watchdog supervision loop and cleanup."""
        self._watchdog.stop()
        try:
            self._fans.cleanup()
            self._profiles.cleanup()
            self._battery.cleanup()
            self._keyboard.cleanup()
            self._sensors.cleanup()
            self._sys_info.cleanup()
        except Exception:
            pass

    def tick(self) -> TelemetrySnapshot:
        """Run a single watchdog tick synchronously (for testing)."""
        return self._watchdog.tick()

    # -----------------------------------------------------------------------
    # API Methods
    # -----------------------------------------------------------------------

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    @property
    def watchdog(self) -> DaemonWatchdog:
        return self._watchdog

    @property
    def fan_manager(self) -> FanControlManager:
        return self._fan_mgr

    @property
    def profile_manager(self) -> ProfileManager:
        return self._profile_mgr

    @property
    def battery_manager(self) -> BatteryController:
        return self._battery_mgr

    @property
    def keyboard_manager(self) -> KeyboardController:
        return self._keyboard_mgr

    @property
    def config_store(self) -> ConfigStore:
        return self._config_store

    def get_state(self) -> DaemonState:
        """Get overall daemon state."""
        profile_state = self._profile_mgr.get_state()
        return DaemonState(
            tier=self._registry.tier,
            tier_reason=self._registry.tier_reason,
            model_profile=self._discovery_result.profile.product_names[0] if (self._discovery_result.profile and self._discovery_result.profile.product_names) else "",
            dmi=self._discovery_result.dmi,
            fan_mode=self._fan_mgr.current_mode,
            fan_lease_active=self._fan_mgr.has_active_lease,
            fan_lease_remaining_s=self._fan_mgr.lease_remaining_s,
            profile=profile_state,
            emergency_override=self._fan_mgr.emergency_override_active,
            mock_mode=self._mock_mode,
            api_version=1,
        )

    def get_telemetry(self) -> TelemetrySnapshot:
        """Get latest telemetry snapshot."""
        return self._watchdog.latest_telemetry

    def get_capabilities(self) -> list[dict[str, Any]]:
        """Get discovered capabilities."""
        return self._registry.get_capabilities_list()

    def get_diagnostics(self) -> DiagnosticReport:
        """Generate structured diagnostic report."""
        return DiagnosticReport(
            timestamp=time.time(),
            dmi=self._discovery_result.dmi,
            tier=self._registry.tier,
            tier_reason=self._registry.tier_reason,
            model_profile=self._discovery_result.profile.product_names[0] if (self._discovery_result.profile and self._discovery_result.profile.product_names) else "",
            kernel_version=self._sys_info.get_kernel_version(),
            distro=self._sys_info.get_distro_info(),
            active_drivers=self._discovery_result.active_drivers,
            capabilities=self.get_capabilities(),
            sensor_failures=[],
            recent_errors=list(self._recent_errors),
            daemon_version="0.1.0",
            mock_mode=self._mock_mode,
            optin_features=[k for k, v in self._registry.optins.items() if v],
        )

    # Fan actions
    def set_fan_mode(self, mode: str, holder: str = "user") -> dict[str, Any]:
        """Set fan mode (auto, max)."""
        mode_str = mode.lower()
        if mode_str == "auto":
            res = self._fan_mgr.set_mode_auto(holder)
        elif mode_str == "max":
            res = self._fan_mgr.set_mode_max(holder)
        else:
            raise ValidationError(f"Invalid fan mode '{mode}'. Use 'auto', 'max', or set_custom_curve", field="mode")
        return res.to_dict()

    def set_custom_curve(
        self,
        holder: str,
        cpu_curve: FanCurve | None = None,
        gpu_curve: FanCurve | None = None,
    ) -> dict[str, Any]:
        """Set custom fan curve."""
        res = self._fan_mgr.set_custom_curve(holder, cpu_curve, gpu_curve)
        return res.to_dict()

    def renew_fan_lease(self, holder: str, duration_s: int = 30) -> bool:
        """Renew active fan lease."""
        return self._fan_mgr.renew_lease(holder, duration_s)

    # Profile actions
    def set_profile(self, profile_name: str) -> dict[str, Any]:
        """Set performance profile (quiet, balanced, performance, turbo)."""
        try:
            lp = LogicalProfile(profile_name.lower())
        except ValueError:
            raise ValidationError(f"Invalid profile name '{profile_name}'", field="profile")
        res = self._profile_mgr.set_profile(lp)
        if res.success:
            self._config.default_profile = lp.value
            try:
                self._config_store.save(self._config)
            except Exception:
                pass
        return res.to_dict()

    # Battery actions
    def set_charge_limit(self, percent: int) -> dict[str, Any]:
        """Set battery charge threshold percentage."""
        res = self._battery_mgr.set_charge_limit(percent)
        if res.success:
            self._config.charge_limit_percent = percent
            self._config.charge_limit_enabled = True
            try:
                self._config_store.save(self._config)
            except Exception:
                pass
        return res.to_dict()

    # Keyboard actions
    def set_keyboard_brightness(self, level: int) -> dict[str, Any]:
        res = self._keyboard_mgr.set_brightness(level)
        if res.success:
            self._config.keyboard_brightness = level
            try:
                self._config_store.save(self._config)
            except Exception:
                pass
        return res.to_dict()

    def set_keyboard_zone_color(self, zone_id: int, r: int, g: int, b: int) -> dict[str, Any]:
        color = RGBColor(r, g, b)
        res = self._keyboard_mgr.set_zone_color(zone_id, color)
        return res.to_dict()

    def set_keyboard_effect(self, effect_name: str, speed: int = 50) -> dict[str, Any]:
        try:
            effect = KeyboardEffect(effect_name.lower())
        except ValueError:
            raise ValidationError(f"Invalid keyboard effect '{effect_name}'", field="effect")
        res = self._keyboard_mgr.set_effect(effect, speed)
        return res.to_dict()

    # Opt-in
    def set_feature_optin(self, feature_id: str, opted_in: bool) -> None:
        """Toggle opt-in for detected tier writes."""
        self._registry.set_optin(feature_id, opted_in)

    def subscribe_telemetry(self, callback: Callable[[TelemetrySnapshot], None]) -> None:
        self._telemetry_subscribers.append(callback)

    def subscribe_alert(self, callback: Callable[[ThermalAlert], None]) -> None:
        self._alert_subscribers.append(callback)

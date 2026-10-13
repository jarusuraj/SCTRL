"""Application-wide constants for SCTRL.

The APP_NAME constant is the single authoritative source for the application
name. Use it in all metadata, logs, paths, and generated documentation.
"""

from pathlib import Path

# -- Application identity --------------------------------------------------

APP_NAME: str = "SCTRL"
APP_ID: str = "io.github.sctrl.sctrl"
APP_DESCRIPTION: str = (
    "Linux laptop monitoring and control utility for supported Acer Nitro "
    "and Predator laptops."
)
APP_VERSION: str = "0.1.0"
APP_LICENSE: str = "GPL-3.0-or-later"

# -- D-Bus ------------------------------------------------------------------

DBUS_BUS_NAME: str = f"{APP_ID}"
DBUS_OBJECT_PATH: str = "/io/github/sctrl/sctrl"
DBUS_INTERFACE: str = f"{APP_ID}.Control"
DBUS_API_VERSION: int = 1

# -- Daemon -----------------------------------------------------------------

DAEMON_NAME: str = "sctrld"
DAEMON_CONFIG_DIR: Path = Path("/etc/sctrl")
DAEMON_CONFIG_FILE: Path = DAEMON_CONFIG_DIR / "config.toml"
DAEMON_PID_FILE: Path = Path("/run/sctrl/sctrld.pid")

# -- Polkit -----------------------------------------------------------------

POLKIT_ACTION_PREFIX: str = f"{APP_ID}"
POLKIT_ACTION_READ: str = f"{POLKIT_ACTION_PREFIX}.read"
POLKIT_ACTION_WRITE: str = f"{POLKIT_ACTION_PREFIX}.write"
POLKIT_ACTION_OPTIN: str = f"{POLKIT_ACTION_PREFIX}.feature-optin"
POLKIT_ACTION_ADMIN: str = f"{POLKIT_ACTION_PREFIX}.admin"

# -- Paths (Linux sysfs) ---------------------------------------------------

SYSFS_DMI_DIR: Path = Path("/sys/class/dmi/id")
SYSFS_HWMON_DIR: Path = Path("/sys/class/hwmon")
SYSFS_THERMAL_DIR: Path = Path("/sys/class/thermal")
SYSFS_POWER_SUPPLY_DIR: Path = Path("/sys/class/power_supply")
SYSFS_PLATFORM_PROFILE: Path = Path("/sys/firmware/acpi/platform_profile")
SYSFS_PLATFORM_PROFILE_CHOICES: Path = Path(
    "/sys/firmware/acpi/platform_profile_choices"
)
SYSFS_PLATFORM_DIR: Path = Path("/sys/devices/platform")
SYSFS_MODULE_DIR: Path = Path("/sys/module")

# -- User configuration (XDG) ----------------------------------------------

XDG_CONFIG_HOME_DEFAULT: str = "~/.config"
USER_CONFIG_DIR_NAME: str = "sctrl"

# -- Timing -----------------------------------------------------------------

DEFAULT_MONITOR_INTERVAL_S: float = 1.0
BATTERY_MONITOR_INTERVAL_S: float = 5.0
MIN_MONITOR_INTERVAL_S: float = 0.5
MAX_MONITOR_INTERVAL_S: float = 30.0

FAN_LEASE_DEFAULT_S: int = 300
FAN_LEASE_MAX_S: int = 3600
FAN_LEASE_RENEW_MARGIN_S: int = 30

THERMAL_WATCHDOG_INTERVAL_S: float = 2.0
STALE_SENSOR_TIMEOUT_S: float = 10.0

# -- Safety defaults --------------------------------------------------------

DEFAULT_CPU_WARN_TEMP_C: int = 90
DEFAULT_CPU_CRITICAL_TEMP_C: int = 100
DEFAULT_GPU_WARN_TEMP_C: int = 85
DEFAULT_GPU_CRITICAL_TEMP_C: int = 95
ALERT_COOLDOWN_S: int = 60

DEFAULT_CHARGE_LIMIT_PERCENT: int = 80
MIN_CHARGE_LIMIT_PERCENT: int = 50
MAX_CHARGE_LIMIT_PERCENT: int = 100

# -- Configuration ----------------------------------------------------------

CONFIG_SCHEMA_VERSION: int = 1

# -- Model database ---------------------------------------------------------

MODELS_DB_DIR_NAME: str = "models_db"

# -- Misc -------------------------------------------------------------------

MAX_HISTORY_POINTS: int = 900  # 15 minutes at 1s interval
DBUS_RATE_LIMIT_PER_S: int = 20
MAX_DIAGNOSTIC_LOG_LINES: int = 500

# -- Notices ----------------------------------------------------------------

UNOFFICIAL_NOTICE: str = (
    f"{APP_NAME} is an unofficial, community-developed project. It is not "
    "affiliated with, endorsed by, or supported by Acer Inc. or any of its "
    "subsidiaries. Use at your own risk."
)

SAFETY_NOTICE: str = (
    f"{APP_NAME} interacts with hardware controls that, if misused, could "
    "potentially cause thermal issues or hardware damage. The developers "
    "provide this software WITHOUT ANY WARRANTY; without even the implied "
    "warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. By "
    "using this software, you acknowledge that you understand the risks "
    "and accept full responsibility for any consequences."
)

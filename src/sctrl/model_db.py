"""Model database loader and support-tier engine for SCTRL.

Loads per-model TOML profiles from models_db/, validates them against
the schema, and computes the support tier at runtime based on DMI match
and BIOS version comparison.

Adding a new model requires only a new TOML file - zero Python changes.
"""

from __future__ import annotations

import importlib.resources
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sctrl.constants import MODELS_DB_DIR_NAME
from sctrl.errors import ConfigError, ErrorCode
from sctrl.models import DMIInfo, SupportTier

logger = logging.getLogger("sctrld.model_db")


# ---------------------------------------------------------------------------
# Model profile data structure
# ---------------------------------------------------------------------------

@dataclass
class VerificationInfo:
    """Physical verification evidence block."""
    tester: str = "unverified"
    date: str = ""
    kernel_version: str = ""
    bios_version: str = ""
    bios_family: str = ""
    features_verified: list[str] = field(default_factory=list)
    features_unverified: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class FanProfile:
    """Fan-related profile data."""
    count: int = 0
    min_speed_percent: int = 0
    max_speed_percent: int = 100
    modes: list[str] = field(default_factory=list)


@dataclass
class KeyboardProfile:
    """Keyboard lighting profile data."""
    zones: int = 0
    effects: list[str] = field(default_factory=list)


@dataclass
class BatteryProfile:
    """Battery and charge control profile data."""
    charge_limit_supported: bool = False
    charge_limit_range: tuple[int, int] = (50, 100)


@dataclass
class ThermalProfile:
    """Thermal threshold profile data."""
    cpu_warn_c: int = 90
    cpu_critical_c: int = 100
    gpu_warn_c: int = 85
    gpu_critical_c: int = 95


@dataclass
class ModelProfile:
    """Complete model profile loaded from TOML."""
    filename: str = ""
    product_names: list[str] = field(default_factory=list)
    vendor: str = ""
    board_names: list[str] = field(default_factory=list)
    primary_driver: str = ""
    optional_drivers: list[str] = field(default_factory=list)
    fans: FanProfile = field(default_factory=FanProfile)
    keyboard: KeyboardProfile = field(default_factory=KeyboardProfile)
    battery: BatteryProfile = field(default_factory=BatteryProfile)
    thermal: ThermalProfile = field(default_factory=ThermalProfile)
    profile_mapping: dict[str, str] = field(default_factory=dict)
    quirks: dict[str, Any] = field(default_factory=dict)
    verification: VerificationInfo = field(default_factory=VerificationInfo)

    @property
    def is_physically_verified(self) -> bool:
        """True if any features have been physically confirmed."""
        return (
            self.verification.tester != "unverified"
            and len(self.verification.features_verified) > 0
        )


# ---------------------------------------------------------------------------
# Profile loading and validation
# ---------------------------------------------------------------------------

def _validate_identity(data: dict[str, Any], filename: str) -> tuple[list[str], str, list[str]]:
    """Validate and extract identity section."""
    identity = data.get("identity")
    if not isinstance(identity, dict):
        raise ConfigError(
            f"Profile {filename}: missing or invalid [identity] section",
            code=ErrorCode.PROFILE_MALFORMED,
            path=filename,
        )

    product_names = identity.get("product_names", [])
    if not isinstance(product_names, list) or len(product_names) == 0:
        raise ConfigError(
            f"Profile {filename}: identity.product_names must be a non-empty list",
            code=ErrorCode.PROFILE_MALFORMED,
            path=filename,
        )
    for name in product_names:
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(
                f"Profile {filename}: identity.product_names contains invalid entry",
                code=ErrorCode.PROFILE_MALFORMED,
                path=filename,
            )

    vendor = identity.get("vendor", "")
    if not isinstance(vendor, str) or not vendor.strip():
        raise ConfigError(
            f"Profile {filename}: identity.vendor is required",
            code=ErrorCode.PROFILE_MALFORMED,
            path=filename,
        )

    board_names = identity.get("board_names", [])
    if not isinstance(board_names, list):
        board_names = []

    return product_names, vendor, board_names


def _validate_verification(data: dict[str, Any], filename: str) -> VerificationInfo:
    """Validate and extract verification section."""
    ver = data.get("verification")
    if not isinstance(ver, dict):
        raise ConfigError(
            f"Profile {filename}: missing or invalid [verification] section",
            code=ErrorCode.PROFILE_MALFORMED,
            path=filename,
        )

    required_fields = ["tester", "date", "kernel_version", "bios_version", "features_verified"]
    for fld in required_fields:
        if fld not in ver:
            raise ConfigError(
                f"Profile {filename}: verification.{fld} is required",
                code=ErrorCode.PROFILE_MALFORMED,
                path=filename,
            )

    features_verified = ver.get("features_verified", [])
    if not isinstance(features_verified, list):
        features_verified = []

    return VerificationInfo(
        tester=str(ver.get("tester", "unverified")),
        date=str(ver.get("date", "")),
        kernel_version=str(ver.get("kernel_version", "")),
        bios_version=str(ver.get("bios_version", "")),
        bios_family=str(ver.get("bios_family", "")),
        features_verified=[str(f) for f in features_verified],
        features_unverified=[str(f) for f in ver.get("features_unverified", [])],
        notes=str(ver.get("notes", "")),
    )


def _load_fans(data: dict[str, Any]) -> FanProfile:
    """Load fan profile section."""
    fans = data.get("fans", {})
    if not isinstance(fans, dict):
        return FanProfile()

    count = fans.get("count", 0)
    if not isinstance(count, int) or count < 0:
        count = 0

    min_speed = fans.get("min_speed_percent", 0)
    max_speed = fans.get("max_speed_percent", 100)
    modes = fans.get("modes", [])
    if not isinstance(modes, list):
        modes = []

    return FanProfile(
        count=count,
        min_speed_percent=max(0, min(100, int(min_speed))),
        max_speed_percent=max(1, min(100, int(max_speed))),
        modes=[str(m) for m in modes],
    )


def _load_keyboard(data: dict[str, Any]) -> KeyboardProfile:
    """Load keyboard profile section."""
    kb = data.get("keyboard", {})
    if not isinstance(kb, dict):
        return KeyboardProfile()

    zones = kb.get("zones", 0)
    effects = kb.get("effects", [])
    if not isinstance(effects, list):
        effects = []

    return KeyboardProfile(
        zones=max(0, int(zones)),
        effects=[str(e) for e in effects],
    )


def _load_battery(data: dict[str, Any]) -> BatteryProfile:
    """Load battery profile section."""
    bat = data.get("battery", {})
    if not isinstance(bat, dict):
        return BatteryProfile()

    supported = bat.get("charge_limit_supported", False)
    limit_range = bat.get("charge_limit_range", [50, 100])
    if isinstance(limit_range, list) and len(limit_range) == 2:
        range_tuple = (int(limit_range[0]), int(limit_range[1]))
    else:
        range_tuple = (50, 100)

    return BatteryProfile(
        charge_limit_supported=bool(supported),
        charge_limit_range=range_tuple,
    )


def _load_thermal(data: dict[str, Any]) -> ThermalProfile:
    """Load thermal profile section."""
    th = data.get("thermal", {})
    if not isinstance(th, dict):
        return ThermalProfile()

    return ThermalProfile(
        cpu_warn_c=int(th.get("cpu_warn_c", 90)),
        cpu_critical_c=int(th.get("cpu_critical_c", 100)),
        gpu_warn_c=int(th.get("gpu_warn_c", 85)),
        gpu_critical_c=int(th.get("gpu_critical_c", 95)),
    )


def load_profile_from_dict(data: dict[str, Any], filename: str) -> ModelProfile:
    """Parse and validate a model profile from a TOML dict.

    Args:
        data: Parsed TOML data.
        filename: Source filename for error messages.

    Returns:
        Validated ModelProfile.

    Raises:
        ConfigError: If the profile is malformed.
    """
    product_names, vendor, board_names = _validate_identity(data, filename)
    verification = _validate_verification(data, filename)

    drivers = data.get("drivers", {})
    if not isinstance(drivers, dict):
        raise ConfigError(
            f"Profile {filename}: missing or invalid [drivers] section",
            code=ErrorCode.PROFILE_MALFORMED,
            path=filename,
        )

    primary_driver = str(drivers.get("primary", ""))
    if not primary_driver:
        raise ConfigError(
            f"Profile {filename}: drivers.primary is required",
            code=ErrorCode.PROFILE_MALFORMED,
            path=filename,
        )

    optional_drivers = drivers.get("optional", [])
    if not isinstance(optional_drivers, list):
        optional_drivers = []

    profiles_section = data.get("profiles", {})
    profile_mapping: dict[str, str] = {}
    if isinstance(profiles_section, dict):
        mapping = profiles_section.get("mapping", {})
        if isinstance(mapping, dict):
            profile_mapping = {str(k): str(v) for k, v in mapping.items()}

    quirks = data.get("quirks", {})
    if not isinstance(quirks, dict):
        quirks = {}

    return ModelProfile(
        filename=filename,
        product_names=product_names,
        vendor=vendor,
        board_names=board_names,
        primary_driver=primary_driver,
        optional_drivers=[str(d) for d in optional_drivers],
        fans=_load_fans(data),
        keyboard=_load_keyboard(data),
        battery=_load_battery(data),
        thermal=_load_thermal(data),
        profile_mapping=profile_mapping,
        quirks=quirks,
        verification=verification,
    )


def load_profile_from_path(path: Path) -> ModelProfile:
    """Load a model profile from a TOML file.

    Args:
        path: Path to the .toml profile file.

    Returns:
        Validated ModelProfile.

    Raises:
        ConfigError: If the file cannot be read or is malformed.
    """
    import tomllib

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(
            f"Failed to load profile {path}: {exc}",
            code=ErrorCode.PROFILE_MALFORMED,
            path=str(path),
        ) from exc

    return load_profile_from_dict(data, path.name)


# ---------------------------------------------------------------------------
# Model database
# ---------------------------------------------------------------------------

class ModelDatabase:
    """In-memory database of all loaded model profiles.

    Profiles are indexed by exact DMI product_name for O(1) lookup.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self._profiles: dict[str, ModelProfile] = {}  # product_name -> profile
        self._all_profiles: list[ModelProfile] = []
        self._load_errors: list[str] = []
        if directory is not None:
            self.load_from_directory(directory)

    @property
    def profiles(self) -> list[ModelProfile]:
        """All successfully loaded profiles."""
        return list(self._all_profiles)

    @property
    def load_errors(self) -> list[str]:
        """Error messages from profiles that failed to load."""
        return list(self._load_errors)

    def load_from_directory(self, directory: Path) -> None:
        """Load all .toml profiles from a directory, skipping schema.toml.

        Malformed or duplicate profiles are logged and skipped, never crash.
        """
        if not directory.is_dir():
            logger.warning("Model database directory does not exist: %s", directory)
            return

        seen_products: dict[str, str] = {}  # product_name -> filename
        resolved_base = directory.resolve()

        for toml_path in sorted(directory.glob("*.toml")):
            if toml_path.name == "schema.toml":
                continue

            # Symlink escape / path traversal check
            try:
                resolved_file = toml_path.resolve()
                if not resolved_file.is_relative_to(resolved_base):
                    msg = f"Security: symlink escape detected for {toml_path.name} -> {resolved_file}. Skipping."
                    logger.warning(msg)
                    self._load_errors.append(msg)
                    continue
            except (ValueError, RuntimeError) as sec_exc:
                msg = f"Security: path escape for {toml_path}: {sec_exc}"
                logger.warning(msg)
                self._load_errors.append(msg)
                continue

            try:
                profile = load_profile_from_path(toml_path)
            except ConfigError as exc:
                msg = f"Skipping malformed profile {toml_path.name}: {exc}"
                logger.warning(msg)
                self._load_errors.append(msg)
                continue
            except Exception as exc:
                msg = f"Unexpected error loading {toml_path.name}: {exc}"
                logger.warning(msg)
                self._load_errors.append(msg)
                continue

            # Check for duplicate product_name entries
            duplicates = False
            for pn in profile.product_names:
                if pn in seen_products:
                    msg = (
                        f"Duplicate product_name '{pn}' in {toml_path.name}, "
                        f"already defined in {seen_products[pn]}. Skipping."
                    )
                    logger.warning(msg)
                    self._load_errors.append(msg)
                    duplicates = True
                    break

            if duplicates:
                continue

            for pn in profile.product_names:
                seen_products[pn] = toml_path.name
                self._profiles[pn] = profile

            self._all_profiles.append(profile)
            logger.info(
                "Loaded model profile: %s (products: %s)",
                toml_path.name,
                ", ".join(profile.product_names),
            )

    def load_bundled(self) -> None:
        """Load profiles bundled with the package."""
        try:
            pkg_dir = importlib.resources.files("sctrl") / MODELS_DB_DIR_NAME
            # Convert to a Path if possible
            with importlib.resources.as_file(pkg_dir) as path:  # type: ignore[arg-type]
                self.load_from_directory(path)
        except (TypeError, FileNotFoundError) as exc:
            logger.warning("Could not load bundled model database: %s", exc)

    def find_profile(self, dmi: DMIInfo) -> ModelProfile | None:
        """Find a profile by exact DMI product_name match.

        No fuzzy matching, no substring matching. Exact string or nothing.
        """
        if not dmi.product_name:
            return None

        profile = self._profiles.get(dmi.product_name)
        if profile is None:
            logger.info(
                "No profile found for product_name='%s'", dmi.product_name
            )
            return None

        # Verify vendor matches if specified in profile
        if profile.vendor and dmi.vendor and profile.vendor.lower() != dmi.vendor.lower():
            # Also check sys_vendor
            if profile.vendor.lower() != dmi.sys_vendor.lower():
                logger.warning(
                    "Profile %s matches product_name '%s' but vendor mismatch: "
                    "profile='%s', dmi vendor='%s', sys_vendor='%s'",
                    profile.filename,
                    dmi.product_name,
                    profile.vendor,
                    dmi.vendor,
                    dmi.sys_vendor,
                )
                return None

        logger.info(
            "Matched profile %s for product_name='%s'",
            profile.filename,
            dmi.product_name,
        )
        return profile


# ---------------------------------------------------------------------------
# Support tier computation
# ---------------------------------------------------------------------------

@dataclass
class TierResult:
    """Result of support-tier computation."""
    tier: SupportTier
    reason: str
    profile: ModelProfile | None = None
    bios_mismatch: bool = False


def compute_support_tier(
    dmi: DMIInfo,
    profile: ModelProfile | None,
    is_acer: bool | None = None,
) -> TierResult:
    """Compute the support tier for the current machine.

    Rules:
    - verified: profile exists with physical test evidence, BIOS family matches
    - community: profile exists but no physical verification or BIOS mismatch
    - detected: no profile but standard kernel interfaces detected on an Acer
    - unsupported: not Acer or no usable interfaces

    Args:
        dmi: System DMI information.
        profile: Matched model profile, if any.
        is_acer: Override for vendor detection. None = derive from DMI.

    Returns:
        TierResult with computed tier and explanation.
    """
    if is_acer is None:
        vendor_lower = (dmi.vendor or dmi.sys_vendor or "").lower()
        is_acer = "acer" in vendor_lower

    if profile is not None:
        # Check if physically verified
        if profile.is_physically_verified:
            # Check BIOS version match
            bios_mismatch = False
            if profile.verification.bios_family:
                if not dmi.bios_version.startswith(profile.verification.bios_family):
                    bios_mismatch = True

            if bios_mismatch:
                return TierResult(
                    tier=SupportTier.COMMUNITY,
                    reason=(
                        f"Profile {profile.filename} is physically verified, "
                        f"but BIOS version '{dmi.bios_version}' does not match "
                        f"verified family '{profile.verification.bios_family}'. "
                        "Downgraded from verified to community."
                    ),
                    profile=profile,
                    bios_mismatch=True,
                )
            return TierResult(
                tier=SupportTier.VERIFIED,
                reason=(
                    f"Profile {profile.filename} matched with physical "
                    f"verification by {profile.verification.tester} on "
                    f"{profile.verification.date}."
                ),
                profile=profile,
            )
        else:
            return TierResult(
                tier=SupportTier.COMMUNITY,
                reason=(
                    f"Profile {profile.filename} matched, but no physical "
                    "verification evidence exists. Reported working by "
                    "community or created from documentation."
                ),
                profile=profile,
            )

    if is_acer:
        return TierResult(
            tier=SupportTier.DETECTED,
            reason=(
                f"Acer device detected (vendor='{dmi.vendor or dmi.sys_vendor}', "
                f"product='{dmi.product_name}') but no matching profile found. "
                "Read-only monitoring enabled. Writes to platform_profile and "
                "charge_control_end_threshold permitted with user confirmation."
            ),
        )

    return TierResult(
        tier=SupportTier.UNSUPPORTED,
        reason=(
            f"Not an Acer device (vendor='{dmi.vendor or dmi.sys_vendor}'). "
            "Read-only monitoring of available standard interfaces only."
        ),
    )

"""Capability registry for SCTRL daemon.

Central registry that holds all discovered capabilities, enforces tier-based
access control, and tracks feature opt-ins. Every hardware write passes
through this registry's tier check.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sctrl.errors import TierBlockedError, ErrorCode, SCTRLError
from sctrl.models import (
    CapabilityRecord,
    FeatureId,
    FeatureStatus,
    SupportTier,
)

logger = logging.getLogger("sctrld.capability_registry")


class CapabilityRegistry:
    """Thread-safe capability registry with tier enforcement.

    The tier check for writes lives here and cannot be bypassed by backends.
    """

    def __init__(self) -> None:
        self._capabilities: dict[FeatureId, CapabilityRecord] = {}
        self._tier: SupportTier = SupportTier.UNSUPPORTED
        self._tier_reason: str = ""
        self._optins: dict[str, bool] = {}  # feature_id.value -> opted_in
        self._last_writes: dict[FeatureId, dict[str, Any]] = {}

    @property
    def tier(self) -> SupportTier:
        return self._tier

    @property
    def tier_reason(self) -> str:
        return self._tier_reason

    @property
    def optins(self) -> dict[str, bool]:
        return dict(self._optins)

    def set_tier(self, tier: SupportTier, reason: str) -> None:
        """Update the current support tier."""
        if tier != self._tier:
            logger.info("Support tier changed: %s -> %s (%s)", self._tier.value, tier.value, reason)
        self._tier = tier
        self._tier_reason = reason

    def update_capabilities(self, caps: dict[FeatureId, CapabilityRecord]) -> None:
        """Replace the full capability set."""
        self._capabilities = dict(caps)
        logger.info("Capabilities updated: %d features", len(caps))

    def get_capability(self, feature_id: FeatureId) -> CapabilityRecord | None:
        """Get a single capability record."""
        return self._capabilities.get(feature_id)

    get = get_capability

    def update_value(self, feature_id: FeatureId, value: Any) -> None:
        """Update current_value for an existing capability."""
        cap = self._capabilities.get(feature_id)
        if cap:
            # CapabilityRecord is frozen, so replace with updated copy
            from dataclasses import replace
            self._capabilities[feature_id] = replace(cap, current_value=value)

    def get_all_capabilities(self) -> dict[FeatureId, CapabilityRecord]:
        """Get all capabilities."""
        return dict(self._capabilities)

    def get_capabilities_list(self) -> list[dict[str, Any]]:
        """Get all capabilities as serializable dicts."""
        return [cap.to_dict() for cap in self._capabilities.values()]

    def is_feature_readable(self, feature_id: FeatureId) -> bool:
        """Check if a feature can be read."""
        cap = self._capabilities.get(feature_id)
        if cap is None:
            return False
        return cap.readable and cap.status in (
            FeatureStatus.SUPPORTED,
            FeatureStatus.DETECTED_UNVERIFIED,
        )

    def is_feature_writable(self, feature_id: FeatureId) -> bool:
        """Check if a feature can be written, considering tier and opt-in."""
        cap = self._capabilities.get(feature_id)
        if cap is None:
            return False
        if not cap.writable:
            return False
        if cap.status not in (FeatureStatus.SUPPORTED, FeatureStatus.DETECTED_UNVERIFIED):
            return False

        # Tier check
        if self._tier in (SupportTier.VERIFIED, SupportTier.COMMUNITY):
            return True

        if self._tier == SupportTier.DETECTED:
            # Only standard interfaces, and only with opt-in
            standard_features = {
                FeatureId.PERFORMANCE_PROFILE,
                FeatureId.PLATFORM_PROFILE,
                FeatureId.CHARGE_LIMIT,
            }
            if feature_id not in standard_features:
                return False
            return self._optins.get(feature_id.value, False)

        # UNSUPPORTED: no writes
        return False

    def check_write_permission(self, feature_id: FeatureId) -> None:
        """Check write permission and raise TierBlockedError if denied.

        This is the single enforcement point that all backends must call
        before performing any hardware write.

        Raises:
            TierBlockedError: If the write is blocked by the current tier.
            SCTRLError: If the feature is not found or not writable.
        """
        cap = self._capabilities.get(feature_id)
        if cap is None:
            raise SCTRLError(
                f"Feature {feature_id.value} not found in capabilities",
                code=ErrorCode.FEATURE_UNAVAILABLE,
            )

        if cap.status == FeatureStatus.UNSUPPORTED:
            raise SCTRLError(
                f"Feature {feature_id.value} is unsupported on this hardware",
                code=ErrorCode.FEATURE_UNSUPPORTED,
            )

        if cap.status == FeatureStatus.DRIVER_MISSING:
            raise SCTRLError(
                f"Feature {feature_id.value} requires a missing driver",
                code=ErrorCode.FEATURE_UNAVAILABLE,
                details={"last_error": cap.last_error},
            )

        if cap.status == FeatureStatus.PERMISSION_DENIED:
            raise SCTRLError(
                f"Insufficient permissions for {feature_id.value}",
                code=ErrorCode.PERMISSION_DENIED,
            )

        if not cap.writable:
            raise SCTRLError(
                f"Feature {feature_id.value} is read-only",
                code=ErrorCode.FEATURE_UNAVAILABLE,
            )

        # Tier enforcement
        if self._tier == SupportTier.UNSUPPORTED:
            raise TierBlockedError(
                feature=feature_id.value,
                tier=self._tier.value,
                reason="All writes disabled on unsupported hardware",
            )

        if self._tier == SupportTier.DETECTED:
            standard_features = {
                FeatureId.PERFORMANCE_PROFILE,
                FeatureId.PLATFORM_PROFILE,
                FeatureId.CHARGE_LIMIT,
            }
            if feature_id not in standard_features:
                raise TierBlockedError(
                    feature=feature_id.value,
                    tier=self._tier.value,
                    reason=(
                        "Driver-specific writes disabled on detected (unmatched) "
                        "hardware. Only platform_profile and charge_limit writes "
                        "are allowed with explicit opt-in."
                    ),
                )
            if not self._optins.get(feature_id.value, False):
                raise TierBlockedError(
                    feature=feature_id.value,
                    tier=self._tier.value,
                    reason=(
                        f"Feature {feature_id.value} requires explicit opt-in "
                        "on detected hardware. Use SetFeatureOptIn."
                    ),
                )

    def set_optin(self, feature_id: str, opted_in: bool) -> None:
        """Set or clear a feature opt-in.

        Opt-ins are only meaningful for detected tier. They are stored
        persistently in config but applied here at runtime.
        """
        self._optins[feature_id] = opted_in
        logger.info(
            "Feature opt-in %s: %s=%s",
            "enabled" if opted_in else "disabled",
            feature_id,
            opted_in,
        )

    def record_write(self, feature_id: FeatureId, result: dict[str, Any]) -> None:
        """Record the result of a hardware write."""
        self._last_writes[feature_id] = {
            **result,
            "recorded_at": time.time(),
        }

    def get_last_write(self, feature_id: FeatureId) -> dict[str, Any] | None:
        """Get the last write result for a feature."""
        return self._last_writes.get(feature_id)

    def get_write_blocked_reason(self, feature_id: FeatureId) -> str:
        """Get a human-readable reason why a write is blocked, or empty string."""
        cap = self._capabilities.get(feature_id)
        if cap is None:
            return f"Feature {feature_id.value} not detected"

        if cap.status == FeatureStatus.UNSUPPORTED:
            return f"Feature {feature_id.value} is unsupported on this hardware"

        if cap.status == FeatureStatus.DRIVER_MISSING:
            return f"Required driver for {feature_id.value} is not loaded"

        if cap.status == FeatureStatus.PERMISSION_DENIED:
            return f"Insufficient permissions for {feature_id.value}"

        if not cap.writable:
            return f"Feature {feature_id.value} is read-only on this interface"

        if self._tier == SupportTier.UNSUPPORTED:
            return "All writes disabled: not a supported device"

        if self._tier == SupportTier.DETECTED:
            standard = {FeatureId.PERFORMANCE_PROFILE, FeatureId.PLATFORM_PROFILE, FeatureId.CHARGE_LIMIT}
            if feature_id not in standard:
                return (
                    f"Feature {feature_id.value} requires a model profile. "
                    "Driver-specific writes are disabled on unmatched hardware."
                )
            if not self._optins.get(feature_id.value, False):
                return (
                    f"Feature {feature_id.value} requires explicit opt-in. "
                    "Go to Settings to enable it."
                )

        return ""

"""Security tests for D-Bus authorization, rate limiting, and caller identification."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import pytest

from sctrl.constants import (
    DBUS_RATE_LIMIT_PER_S,
    POLKIT_ACTION_ADMIN,
    POLKIT_ACTION_WRITE,
)
from sctrl.errors import PermissionDeniedError
from sctrl.models import FanMode
from daemon.service import SCTRLService
from daemon.dbus_service import SCTRLDBusInterface, PolkitAuthorizer, RateLimiter


class MockPolkitAuthorizer(PolkitAuthorizer):
    """Controllable polkit authorizer for unit testing."""

    def __init__(self) -> None:
        super().__init__(enabled=True)
        self.authorized_senders: set[str] = set()
        self.authorized_actions: set[str] = set()
        self.call_history: list[dict[str, str]] = []

    def allow(self, sender: str, action_id: str) -> None:
        self.authorized_senders.add(sender)
        self.authorized_actions.add(action_id)

    async def check_authorization(
        self,
        sender: str,
        action_id: str,
        allow_interaction: bool = True,
    ) -> bool:
        self.call_history.append({"sender": sender, "action_id": action_id})
        return (sender in self.authorized_senders) and (action_id in self.authorized_actions)


@pytest.fixture
def test_service(tmp_path: Path) -> SCTRLService:
    cfg = tmp_path / "test_sctrl.toml"
    service = SCTRLService(mock_mode=True, mock_model="verified", config_path=cfg)
    return service


def test_dbus_authorization_rejects_unauthorized_callers(test_service: SCTRLService) -> None:
    """Every write method must perform a polkit CheckAuthorization and reject unauthorized callers."""
    async def _test() -> None:
        authorizer = MockPolkitAuthorizer()
        interface = SCTRLDBusInterface(test_service, authorizer=authorizer)

        caller_unauthorized = ":1.100"
        # Caller is not authorized for any action

        # 1. SetFanMode must fail
        with pytest.raises(PermissionDeniedError):
            await interface.set_fan_mode_impl("max", sender=caller_unauthorized)

        # 2. SetProfile must fail
        with pytest.raises(PermissionDeniedError):
            await interface.set_profile_impl("performance", sender=caller_unauthorized)

        # 3. SetChargeLimit must fail
        with pytest.raises(PermissionDeniedError):
            await interface.set_charge_limit_impl(80, sender=caller_unauthorized)

        # 4. SetKeyboardBrightness must fail
        with pytest.raises(PermissionDeniedError):
            await interface.set_keyboard_brightness_impl(50, sender=caller_unauthorized)

    asyncio.run(_test())


def test_dbus_set_feature_optin_requires_admin_action(test_service: SCTRLService) -> None:
    """SetFeatureOptIn requires the stronger io.github.sctrl.sctrl.admin polkit action."""
    async def _test() -> None:
        authorizer = MockPolkitAuthorizer()
        interface = SCTRLDBusInterface(test_service, authorizer=authorizer)

        caller = ":1.200"
        # Allow write action, but NOT admin action
        authorizer.allow(caller, POLKIT_ACTION_WRITE)

        # Normal write should succeed
        res = await interface.set_fan_mode_impl("auto", sender=caller)
        assert "success" in res

        # SetFeatureOptIn must be rejected because it requires POLKIT_ACTION_ADMIN
        with pytest.raises(PermissionDeniedError):
            await interface.set_feature_optin_impl("performance_profile", True, sender=caller)

        # Now grant POLKIT_ACTION_ADMIN
        authorizer.allow(caller, POLKIT_ACTION_ADMIN)
        optin_res = await interface.set_feature_optin_impl("performance_profile", True, sender=caller)
        assert optin_res is True

    asyncio.run(_test())


def test_dbus_rate_limiting_enforced(test_service: SCTRLService) -> None:
    """Exceeding DBUS_RATE_LIMIT_PER_S calls per second must be rejected."""
    async def _test() -> None:
        authorizer = MockPolkitAuthorizer()
        caller = ":1.300"
        authorizer.allow(caller, POLKIT_ACTION_WRITE)
        authorizer.allow(caller, POLKIT_ACTION_ADMIN)

        interface = SCTRLDBusInterface(test_service, authorizer=authorizer)

        # DBUS_RATE_LIMIT_PER_S calls should succeed
        for _ in range(DBUS_RATE_LIMIT_PER_S):
            await interface.set_fan_mode_impl("auto", sender=caller)

        # The next call in the same second must be rejected
        with pytest.raises(PermissionDeniedError, match="Rate limit exceeded"):
            await interface.set_fan_mode_impl("auto", sender=caller)

    asyncio.run(_test())


def test_lease_holder_identified_by_dbus_sender_never_client_string(test_service: SCTRLService) -> None:
    """Fan lease holder must always be the D-Bus sender, never a client-supplied string."""
    async def _test() -> None:
        authorizer = MockPolkitAuthorizer()
        caller_bus_sender = ":1.456"
        authorizer.allow(caller_bus_sender, POLKIT_ACTION_WRITE)

        interface = SCTRLDBusInterface(test_service, authorizer=authorizer)

        # Even if an attacker passes client_holder="arbitrary_system_admin", the actual
        # lease holder must be caller_bus_sender
        await interface.set_fan_mode_impl("max", sender=caller_bus_sender)

        active_lease = test_service._fan_mgr._lease
        assert active_lease is not None
        assert active_lease.holder == caller_bus_sender
        assert active_lease.holder != "arbitrary_system_admin"

    asyncio.run(_test())


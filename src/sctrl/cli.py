"""Command-line interface for SCTRL.

Allows controlling fans, performance profiles, battery charging threshold,
and querying diagnostics from the terminal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sctrl.constants import VERSION


def print_status(state: dict[str, Any], telemetry: dict[str, Any]) -> None:
    print(f"=== SCTRL v{VERSION} Status ===")
    tier = state.get("tier", "unknown").upper()
    print(f"Support Tier:   {tier} ({state.get('tier_reason', '')})")
    dmi = state.get("dmi", {})
    print(f"Hardware Model: {dmi.get('product_name', 'Unknown')} ({dmi.get('board_name', '')})")
    print(f"BIOS Version:   {dmi.get('bios_version', 'Unknown')}")
    print(f"Mock Mode:      {state.get('mock_mode', False)}")
    print("----------------------------------------")

    # Telemetry
    cpu_t = telemetry.get("cpu_temp", {}).get("value")
    gpu_t = telemetry.get("gpu_temp", {}).get("value")
    print(f"CPU Temp:       {f'{cpu_t:.1f}°C' if cpu_t is not None else 'N/A'}")
    print(f"GPU Temp:       {f'{gpu_t:.1f}°C' if gpu_t is not None else 'N/A'}")

    cpu_rpm = telemetry.get("cpu_fan_rpm", {}).get("value")
    gpu_rpm = telemetry.get("gpu_fan_rpm", {}).get("value")
    print(f"CPU Fan:        {f'{int(cpu_rpm)} RPM' if cpu_rpm is not None else 'N/A'}")
    print(f"GPU Fan:        {f'{int(gpu_rpm)} RPM' if gpu_rpm is not None else 'N/A'}")

    bat_pct = telemetry.get("battery_percent", {}).get("value")
    bat_state = telemetry.get("battery_state", "unknown")
    chg_limit = telemetry.get("charge_limit", {}).get("value")
    print(f"Battery:        {f'{bat_pct:.0f}%' if bat_pct is not None else 'N/A'} ({bat_state})")
    print(f"Charge Limit:   {f'{int(chg_limit)}%' if chg_limit is not None else 'Disabled/Unsupported'}")

    prof = state.get("profile", {})
    print(f"Profile:        {prof.get('applied', 'N/A')} (available: {', '.join(prof.get('available_profiles', []))})")
    print(f"Fan Mode:       {state.get('fan_mode', 'auto')}")
    print("========================================")


def main() -> None:
    parser = argparse.ArgumentParser(prog="sctrl", description=f"SCTRL CLI v{VERSION}")
    parser.add_argument("--mock", action="store_true", help="Run with local mock backend")
    parser.add_argument("--tier", default="verified", help="Mock tier (verified, community, detected, unsupported)")

    subparsers = parser.add_subparsers(dest="command")

    # status
    subparsers.add_parser("status", help="Show current system status and telemetry")

    # fan
    fan_parser = subparsers.add_parser("fan", help="Fan control commands")
    fan_sub = fan_parser.add_subparsers(dest="fan_command")
    fan_sub.add_parser("auto", help="Set fans to firmware automatic control")
    fan_sub.add_parser("max", help="Set fans to maximum speed")

    # profile
    prof_parser = subparsers.add_parser("profile", help="Performance profile control")
    prof_parser.add_argument("name", choices=["quiet", "balanced", "performance", "turbo"], help="Profile name")

    # battery
    bat_parser = subparsers.add_parser("battery", help="Battery charge limit control")
    bat_sub = bat_parser.add_subparsers(dest="battery_command")
    limit_parser = bat_sub.add_parser("limit", help="Set battery charge limit percentage")
    limit_parser.add_argument("percent", type=int, help="Percentage limit (e.g. 80)")

    # diagnostics
    subparsers.add_parser("diagnostics", help="Generate and print diagnostic report")

    args = parser.parse_args()

    # Create local service instance (handles mock or direct call)
    from daemon.service import SCTRLService
    service = SCTRLService(mock_mode=args.mock, mock_model=args.tier)
    service.tick()

    if args.command == "status" or args.command is None:
        state = service.get_state().to_dict()
        telemetry = service.get_telemetry().to_dict()
        print_status(state, telemetry)
    elif args.command == "fan":
        if args.fan_command in ("auto", "max"):
            res = service.set_fan_mode(args.fan_command)
            print(f"Fan mode set to {args.fan_command}: {res}")
        else:
            fan_parser.print_help()
    elif args.command == "profile":
        res = service.set_profile(args.name)
        print(f"Profile set to {args.name}: {res}")
    elif args.command == "battery":
        if args.battery_command == "limit":
            res = service.set_charge_limit(args.percent)
            print(f"Charge limit set to {args.percent}%: {res}")
        else:
            bat_parser.print_help()
    elif args.command == "diagnostics":
        diag = service.get_diagnostics().to_dict()
        print(json.dumps(diag, indent=2))


if __name__ == "__main__":
    main()

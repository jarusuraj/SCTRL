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
    parser.add_argument("--discover", action="store_true", help="Run read-only hardware discovery and print capabilities without any writes")

    subparsers = parser.add_subparsers(dest="command")

    # discover
    subparsers.add_parser("discover", help="Run read-only discovery mode and display capabilities")

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

    # report-model (Redacted, local only, zero network)
    report_parser = subparsers.add_parser("report-model", help="Generate redacted model report (local file or stdout, zero network)")
    report_parser.add_argument("--output", "-o", help="Output file path (default: stdout)")

    args = parser.parse_args()

    from daemon.service import SCTRLService

    if args.discover or args.command == "discover":
        service = SCTRLService(mock_mode=args.mock, mock_model=args.tier, read_only_discovery=True)
        diag = service.get_diagnostics().to_dict()
        print("=== SCTRL Read-Only Hardware Discovery ===")
        print(f"Product:   {diag['dmi']['product_name']} ({diag['dmi']['board_name']})")
        print(f"Vendor:    {diag['dmi']['vendor']}")
        print(f"BIOS:      {diag['dmi']['bios_version']}")
        print(f"Tier:      {diag['tier'].upper()} - {diag['tier_reason']}")
        print(f"Drivers:   {', '.join(diag['active_drivers'])}")
        print("\nCapabilities Discovered:")
        for cap in diag['capabilities']:
            r_w = f"[{'R' if cap['readable'] else '-'}{'W' if cap['writable'] else '-'}]"
            print(f"  {r_w} {cap['feature_id']:<22} status={cap['status']:<12} iface={cap['interface']}")
        print("==========================================")
        return

    # Create local service instance (handles mock or direct call)
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
    elif args.command == "report-model":
        diag = service.get_diagnostics().to_dict()
        dmi = diag.get("dmi", {})
        redacted_dmi = {
            "product_name": dmi.get("product_name", "Unknown"),
            "board_name": dmi.get("board_name", "Unknown"),
            "vendor": dmi.get("vendor", "Unknown"),
            "bios_version": dmi.get("bios_version", "Unknown"),
            "bios_date": dmi.get("bios_date", "Unknown"),
            "serial_number": "[REDACTED]",
            "uuid": "[REDACTED]",
            "chassis_type": dmi.get("chassis_type", "Unknown"),
        }
        report = {
            "report_type": "sctrl_hardware_model_report",
            "notice": "Redacted local dump for contributing hardware model profiles. Zero network transmission.",
            "dmi": redacted_dmi,
            "tier": diag.get("tier"),
            "tier_reason": diag.get("tier_reason"),
            "active_drivers": diag.get("active_drivers", []),
            "capabilities": [
                {
                    "feature_id": c.get("feature_id"),
                    "status": c.get("status"),
                    "interface": c.get("interface"),
                    "readable": c.get("readable"),
                    "writable": c.get("writable"),
                }
                for c in diag.get("capabilities", [])
            ],
        }
        report_str = json.dumps(report, indent=2)
        if args.output:
            out_path = Path(args.output)
            out_path.write_text(report_str, encoding="utf-8")
            print(f"Redacted model report written to {out_path}")
        else:
            print(report_str)


if __name__ == "__main__":
    main()


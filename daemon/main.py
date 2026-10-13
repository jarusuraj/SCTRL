"""Entry point for sctrld daemon.

Parses command line arguments, configures logging, initializes the SCTRLService,
and starts the D-Bus interface and watchdog supervision loop.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from sctrl.constants import DAEMON_NAME, LOG_FILE, VERSION
from sctrl.logging_config import setup_logging
from daemon.dbus_service import DBusServer
from daemon.service import SCTRLService

logger = logging.getLogger("sctrld")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sctrld",
        description=f"SCTRL Daemon v{VERSION} - Hardware control and monitoring for Acer laptops",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Run in mock hardware mode (never touches real hardware, safe for testing)",
    )
    parser.add_argument(
        "--tier",
        choices=["verified", "community", "detected", "unsupported", "bios_mismatch"],
        default="verified",
        help="Simulated model support tier in mock mode (default: verified)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to custom daemon config file",
    )
    parser.add_argument(
        "--models",
        type=Path,
        default=None,
        help="Path to models_db directory",
    )
    parser.add_argument(
        "--session-bus",
        action="store_true",
        help="Connect to D-Bus session bus instead of system bus (for testing)",
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Run standalone engine without connecting to D-Bus",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


async def run_daemon(args: argparse.Namespace) -> None:
    level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(level=level, log_file=LOG_FILE if not args.mock else None)

    logger.info("Starting SCTRL Daemon v%s", VERSION)
    if args.mock:
        logger.info("Running in SIMULATION / MOCK mode (tier: %s)", args.tier)

    service = SCTRLService(
        mock_mode=args.mock,
        mock_model=args.tier,
        config_path=args.config,
        models_dir=args.models,
    )

    service.start()

    dbus_server: DBusServer | None = None
    if not args.standalone:
        dbus_server = DBusServer(service, use_session_bus=args.session_bus)
        await dbus_server.start()

    # Graceful shutdown event
    stop_event = asyncio.Event()

    def _sig_handler(*_: object) -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    # Register signal handlers on platforms that support them
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except (NotImplementedError, AttributeError):
            # Windows or non-main thread fallback
            signal.signal(sig, lambda *args: stop_event.set())

    logger.info("SCTRL Daemon is operational and ready")

    try:
        await stop_event.wait()
    finally:
        logger.info("Stopping SCTRL Daemon...")
        if dbus_server:
            await dbus_server.stop()
        service.stop()
        logger.info("SCTRL Daemon shutdown complete")


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(run_daemon(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

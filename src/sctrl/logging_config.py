"""Logging configuration for SCTRL.

Sets up structured logging with journald integration when available,
falling back to stderr. Prevents repeated error flooding.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from sctrl.constants import APP_NAME, DAEMON_NAME


class RateLimitFilter(logging.Filter):
    """Suppress repeated identical messages within a cooldown period."""

    def __init__(self, cooldown_s: float = 10.0) -> None:
        super().__init__()
        self._cooldown_s = cooldown_s
        self._last_seen: dict[str, float] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        import time

        key = f"{record.name}:{record.levelno}:{record.getMessage()}"
        now = time.monotonic()
        last = self._last_seen.get(key, 0.0)
        if now - last < self._cooldown_s:
            return False
        self._last_seen[key] = now
        return True


def setup_logging(
    name: str = DAEMON_NAME,
    level: int = logging.INFO,
    use_journald: bool = False,
    rate_limit_s: float = 10.0,
) -> logging.Logger:
    """Configure and return the application logger.

    Args:
        name: Logger name, typically the daemon or GUI name.
        level: Logging level.
        use_journald: Attempt journald integration via systemd.journal.
        rate_limit_s: Suppress duplicate messages within this window.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Prevent adding handlers multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt=f"%(asctime)s [{APP_NAME}] %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler: logging.Handler

    if use_journald:
        try:
            from systemd.journal import JournalHandler  # type: ignore[import-untyped]

            handler = JournalHandler(SYSLOG_IDENTIFIER=name)
        except ImportError:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)

    if rate_limit_s > 0:
        handler.addFilter(RateLimitFilter(cooldown_s=rate_limit_s))

    logger.addHandler(handler)
    return logger


def get_logger(module_name: str) -> logging.Logger:
    """Get a child logger for a specific module.

    Args:
        module_name: Dotted module path.

    Returns:
        Logger scoped to the module.
    """
    return logging.getLogger(f"{DAEMON_NAME}.{module_name}")

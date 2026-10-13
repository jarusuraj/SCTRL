# Third-Party Dependencies and Licenses

SCTRL makes use of the following third-party software and libraries:

## Runtime Dependencies

### dbus-next
- **License**: MIT License
- **Copyright**: (c) Tony Crisci
- **Source**: https://github.com/altdesktop/python-dbus-next
- **Description**: Python library for D-Bus communication designed for high-performance async workflows.

### psutil
- **License**: BSD-3-Clause
- **Copyright**: (c) 2009, Jay Loden, Dave Daeschler, Giampaolo Rodola
- **Source**: https://github.com/giampaolo/psutil
- **Description**: Cross-platform process and system monitoring library used for CPU, RAM, and system uptime telemetry.

### PySide6 (Optional GUI Dependency)
- **License**: LGPL-3.0
- **Copyright**: (c) The Qt Company
- **Source**: https://www.qt.io/
- **Description**: Official Python bindings for the Qt application framework.

## Development & Test Dependencies

### pytest
- **License**: MIT License
- **Copyright**: (c) Holger Krekel and pytest-dev team
- **Source**: https://github.com/pytest-dev/pytest

### ruff
- **License**: MIT License / Apache-2.0
- **Copyright**: (c) Astral Software Inc.
- **Source**: https://github.com/astral-sh/ruff

### mypy
- **License**: MIT License
- **Copyright**: (c) Jukka Lehtosalo and contributors
- **Source**: https://github.com/python/mypy

## Linux Kernel & Community Drivers Referenced

### linuwu-sense
- **License**: GPL-2.0
- **Source**: https://github.com/Jovian-Experiments/linuwu-sense
- **Description**: Community Linux kernel module for fan, RGB, and thermal management on Acer gaming laptops. SCTRL interacts with the sysfs interface provided by this driver when loaded.

### acer-wmi
- **License**: GPL-2.0
- **Description**: Upstream Linux kernel platform driver for Acer hardware.

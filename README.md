# SCTRL (Suraj Control)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python: 3.12+](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](pyproject.toml)

**SCTRL** is an original Linux laptop monitoring and control center designed for supported Acer Nitro and Predator laptops. It provides power-users with fan curve customization, performance profile switching, 80% battery health protection, multi-zone RGB lighting, and hardware telemetry without relying on proprietary utilities or waking suspended discrete GPUs.

> **Disclaimer**: SCTRL is an unofficial, community-developed utility. It is not affiliated with, endorsed by, or supported by Acer Inc.

---

## Architecture

SCTRL is built with a privilege-separated, safety-first architecture:

```
┌────────────────────────────────────────────────────────┐
│                   sctrl-gui (PySide6)                  │
│             sctrl (Command-Line Utility)               │
└──────────────────────────┬─────────────────────────────┘
                           │ D-Bus (io.github.sctrl.sctrl)
                           ▼
┌────────────────────────────────────────────────────────┐
│                 sctrld (Root Daemon)                   │
│  ├── Watchdog & Telemetry Engine                       │
│  ├── Fan Lease Manager & Safety Watchdog               │
│  ├── Thermal Threshold Policy (Emergency Override)     │
│  ├── Battery Health Controller (Charge Limiter)        │
│  ├── Performance Profile Manager (ACPI platform)       │
│  └── Capability Registry & Runtime Tier Engine         │
└──────────────────────────┬─────────────────────────────┘
                           │ Hardware Abstraction Layer
                           ▼
┌────────────────────────────────────────────────────────┐
│  /sys/class/hwmon  │  /sys/firmware/acpi  │  /sys/power │
│  acer-wmi driver   │  NVIDIA PCI (RTD3)   │  Mock HAL   │
└────────────────────────────────────────────────────────┘
```

1. **`sctrld` (System Daemon)**: Runs as a root systemd service. Owns all hardware reads/writes, enforces monotonic slope constraints, monitors lease timeouts, triggers emergency cooling overrides, and exports the `io.github.sctrl.sctrl` D-Bus interface.
2. **`sctrl-gui` (Desktop Interface)**: Modern, responsive dark-mode GUI built with PySide6. Features dynamic sensor gauges, interactive 2D fan curve plots, one-click profile switching, and battery threshold sliders.
3. **`sctrl` (CLI)**: Fast command-line interface for querying status, switching profiles, setting fan modes, and printing structured JSON diagnostics.
4. **Model Database**: Zero-code TOML profiles in `src/sctrl/models_db/` mapping DMI identifiers, drivers, and platform quirks.

---

## Support Tiers

Every device is dynamically classified at boot into one of four support tiers:

| Tier | Definition | Permissions |
| :--- | :--- | :--- |
| **Verified** | Model confirmed by physical testing with documented test matrix. | Full read and write controls enabled. |
| **Community** | Model profile contributed and reported working by users. | Full read and write controls enabled. |
| **Detected** | Acer laptop detected without an exact model profile. | Standard ACPI reads enabled; writes require explicit opt-in. |
| **Unsupported** | Non-Acer or incompatible hardware. | Purely read-only monitoring; all writes permanently blocked. |

---

## Safety Features

- **Lease-Based Fan Control**: Manual and custom fan modes require continuous client lease renewal. If the client closes, crashes, or unhooks, fans revert automatically to firmware auto control.
- **Independent Thermal Watchdog**: Monitors CPU and GPU temperatures independently of user settings. If critical thresholds are breached, fans are immediately forced to maximum speed until cooldown completes.
- **Monotonic Curve Validation**: Fan curves are strictly validated before acceptance (non-decreasing speeds, minimum dwell times, and hysteresis to prevent oscillation).
- **dGPU Suspend Awareness**: Explicitly inspects PCI `runtime_status` prior to telemetry queries to avoid waking up discrete GPUs from power-saving runtime suspend (RTD3).

---

## Installation & Development

### Setting up the Environment

```bash
# Clone the repository
git clone https://github.com/jarusuraj/SCTRL.git
cd SCTRL


# Initialize Python virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### Running the Test Suite

```bash
pytest -v
```

### Running in Mock Mode

You can test all daemon and CLI features safely without touching physical hardware:

```bash
# Query mock status
python -m sctrl.cli --mock status

# Set fan mode to max
python -m sctrl.cli --mock fan max

# Switch performance profile
python -m sctrl.cli --mock profile turbo

# Set battery charge limit
python -m sctrl.cli --mock battery limit 80

# Inspect structured diagnostics
python -m sctrl.cli --mock diagnostics
```

---

## System Integration (Linux Deployment)

Package integration files are located in `packaging/`:
- **Systemd Service**: `packaging/sctrld.service`
- **D-Bus Configuration**: `packaging/io.github.sctrl.sctrl.conf`
- **Polkit Policy**: `packaging/io.github.sctrl.sctrl.policy`
- **Desktop Entry**: `packaging/io.github.sctrl.sctrl.desktop`

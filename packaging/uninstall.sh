#!/usr/bin/env bash
set -euo pipefail

# SCTRL Uninstallation Script
# Must be executed as root

if [[ $EUID -ne 0 ]]; then
   echo "Error: SCTRL uninstallation requires root privileges." >&2
   exit 1
fi

echo "Uninstalling SCTRL..."

# 1. Stop and disable systemd service
if systemctl is-active --quiet sctrld.service 2>/dev/null; then
    systemctl stop sctrld.service || true
fi
systemctl disable sctrld.service 2>/dev/null || true

# 2. Remove installed system integration files
rm -f /etc/systemd/system/sctrld.service
rm -f /etc/dbus-1/system.d/io.github.sctrl.sctrl.conf
rm -f /usr/share/polkit-1/actions/io.github.sctrl.sctrl.policy
rm -f /usr/share/applications/io.github.sctrl.sctrl.desktop

# 3. Reload system managers
systemctl daemon-reload
systemctl reload dbus 2>/dev/null || true

# 4. Uninstall Python package
pip uninstall -y sctrl 2>/dev/null || true

echo "SCTRL uninstalled successfully."

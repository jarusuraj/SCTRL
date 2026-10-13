#!/usr/bin/env bash
set -euo pipefail

# SCTRL Installation Script
# Must be executed as root

if [[ $EUID -ne 0 ]]; then
   echo "Error: SCTRL installation requires root privileges." >&2
   exit 1
fi

echo "Installing SCTRL (Suraj Control)..."

# 1. Install system configuration directories
mkdir -p /etc/sctrl
mkdir -p /var/log/sctrl
mkdir -p /run/sctrl
chmod 755 /etc/sctrl /var/log/sctrl /run/sctrl

# 2. Install D-Bus system bus configuration
install -m 644 packaging/io.github.sctrl.sctrl.conf /etc/dbus-1/system.d/io.github.sctrl.sctrl.conf

# 3. Install Polkit Policy
install -m 644 packaging/io.github.sctrl.sctrl.policy /usr/share/polkit-1/actions/io.github.sctrl.sctrl.policy

# 4. Install systemd service
install -m 644 packaging/sctrld.service /etc/systemd/system/sctrld.service

# 5. Install Desktop entry
if [[ -d /usr/share/applications ]]; then
    install -m 644 packaging/io.github.sctrl.sctrl.desktop /usr/share/applications/io.github.sctrl.sctrl.desktop
fi

# 6. Install Python package
pip install .

# 7. Reload system services
echo "Reloading systemd and D-Bus..."
systemctl daemon-reload
systemctl reload dbus || true

echo "Enabling and starting sctrld..."
systemctl enable sctrld.service
systemctl restart sctrld.service

echo "SCTRL installation complete!"

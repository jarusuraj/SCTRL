#!/usr/bin/env bash
set -euo pipefail

# SCTRL Debian package builder

PKG_NAME="sctrl"
VERSION="0.1.0"
ARCH="all"
BUILD_DIR="build/debian/${PKG_NAME}_${VERSION}_${ARCH}"

echo "Building Debian package for SCTRL ${VERSION}..."

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/usr/lib/python3/dist-packages"
mkdir -p "${BUILD_DIR}/usr/bin"
mkdir -p "${BUILD_DIR}/etc/sctrl"
mkdir -p "${BUILD_DIR}/etc/dbus-1/system.d"
mkdir -p "${BUILD_DIR}/usr/share/polkit-1/actions"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/lib/systemd/system"

# Control metadata
cat > "${BUILD_DIR}/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: admin
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.12), python3-psutil, python3-dbus-next
Maintainer: SCTRL Contributors <jarusuraj@users.noreply.github.com>
Description: SCTRL - Linux laptop control utility for Acer Nitro and Predator
 Hardware control daemon, CLI, and desktop utility for custom fan curves,
 performance profile management, battery health protection, and monitoring.
EOF

# Copy integration files
cp packaging/io.github.sctrl.sctrl.conf "${BUILD_DIR}/etc/dbus-1/system.d/"
cp packaging/io.github.sctrl.sctrl.policy "${BUILD_DIR}/usr/share/polkit-1/actions/"
cp packaging/io.github.sctrl.sctrl.desktop "${BUILD_DIR}/usr/share/applications/"
cp packaging/sctrld.service "${BUILD_DIR}/lib/systemd/system/"

# Post-install hook
cat > "${BUILD_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
systemctl daemon-reload || true
systemctl reload dbus || true
exit 0
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

# Build package
dpkg-deb --build "${BUILD_DIR}" "build/${PKG_NAME}_${VERSION}_${ARCH}.deb"
echo "Package built at build/${PKG_NAME}_${VERSION}_${ARCH}.deb"

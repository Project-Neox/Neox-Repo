#!/usr/bin/env bash
# Ornek/ilk paket: neox-repo-setup (depoyu sisteme ekleyen yardimci araci)
# Kullanim: scripts/build-sample-package.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PKG="$WORK/neox-repo-setup"
mkdir -p "$PKG/DEBIAN" "$PKG/usr/bin" "$PKG/usr/share/doc/neox-repo-setup"

cat > "$PKG/DEBIAN/control" <<'EOF'
Package: neox-repo-setup
Version: 1.0.0
Section: admin
Priority: optional
Architecture: all
Maintainer: Project Neox <apt@project-neox.github.io>
Depends: curl
Description: Neox APT deposunu Debian/Ubuntu sistemine ekler
 Neox APT deposunu (https://project-neox.github.io/Neox-Repo) ve
 GPG imzalama anahtarini bu sisteme kurar.
 .
 Kurulumdan sonra `sudo apt update` ile depodaki paketler kullanilabilir.
EOF

install -m 0755 "$ROOT/scripts/setup-repo.sh" "$PKG/usr/bin/neox-repo-setup"

cat > "$PKG/usr/share/doc/neox-repo-setup/copyright" <<'EOF'
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: neox-repo-setup
Source: https://github.com/Project-Neox/Neox-Repo

Files: *
Copyright: 2026 Project Neox
License: MIT
 Permission is hereby granted, free of charge, to any person obtaining a copy
 of this software and associated documentation files (the "Software"), to deal
 in the Software without restriction.
 .
 On Debian systems, the full text of the MIT license is available at
 /usr/share/common-licenses/MIT.
EOF

mkdir -p "$ROOT/pool"
OUT="$ROOT/pool/neox-repo-setup_1.0.0_all.deb"
dpkg-deb --root-owner-group --build "$PKG" "$OUT"
echo "Olusturuldu: pool/neox-repo-setup_1.0.0_all.deb"
dpkg-deb --info "$OUT" | head -12

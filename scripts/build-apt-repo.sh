#!/usr/bin/env bash
# Neox APT deposunu imzasiz olarak derler.
#
# Yaptiklari:
#   1) pool/ icindeki .deb'leri staging havuzuna kopyalar
#   2) dists/stable/ metadata'sini (Packages, Packages.gz, Release) uretir
#   3) site dosyalarini ve yardimci scriptleri staging'e kopyalar
#   4) packages.json dosyasini uretir
#
# Kullanim: scripts/build-apt-repo.sh [STAGING_DIR] (varsayilan: public/)
# Not: APT kaynagi istemcilerde [trusted=yes] ile eklenmelidir.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="${1:-$ROOT/public}"

SUITE="stable"
COMPONENT="main"
ARCH="amd64"
ORIGIN="Neox"
LABEL="Neox-Repo"
DESCRIPTION="Neox APT Repository - Project-Neox"

echo "==> Staging hazirlaniyor: $STAGING"
rm -rf "$STAGING"
mkdir -p "$STAGING"
STAGING="$(cd "$STAGING" && pwd)"
DIST="$STAGING/dists/$SUITE"
BIN="$DIST/$COMPONENT/binary-$ARCH"
mkdir -p "$BIN" "$STAGING/pool"
touch "$STAGING/.nojekyll"

# 1) .deb'leri havuza kopyala
shopt -s nullglob
DEBS=("$ROOT"/pool/*.deb)
if [ "${#DEBS[@]}" -eq 0 ]; then
    echo "UYARI: pool/ dizininde .deb bulunamadi!"
else
    cp "${DEBS[@]}" "$STAGING/pool/"
    echo "==> ${#DEBS[@]} paket havuza kopyalandi"
fi

# 2) Packages indexleri (Filename: pool/... olmasi icin STAGING icinde calis)
cd "$STAGING"
if command -v apt-ftparchive >/dev/null 2>&1; then
    apt-ftparchive packages pool > "$BIN/Packages"
    echo "==> Packages uretildi (apt-ftparchive)"
elif command -v dpkg-scanpackages >/dev/null 2>&1; then
    dpkg-scanpackages --multiversion pool /dev/null > "$BIN/Packages" 2>/dev/null
    echo "==> Packages uretildi (dpkg-scanpackages)"
else
    echo "HATA: apt-ftparchive veya dpkg-scanpackages gerekli" >&2
    exit 1
fi
gzip -9c "$BIN/Packages" > "$BIN/Packages.gz"

# 3) Release metadata (GPG imzasi uretilmez)
if command -v apt-ftparchive >/dev/null 2>&1; then
    apt-ftparchive \
        -o APT::FTPArchive::Release::Origin="$ORIGIN" \
        -o APT::FTPArchive::Release::Label="$LABEL" \
        -o APT::FTPArchive::Release::Suite="$SUITE" \
        -o APT::FTPArchive::Release::Codename="$SUITE" \
        -o APT::FTPArchive::Release::Architectures="$ARCH" \
        -o APT::FTPArchive::Release::Components="$COMPONENT" \
        -o APT::FTPArchive::Release::Description="$DESCRIPTION" \
        release "$DIST" > "$DIST/Release"
    echo "==> Release uretildi (apt-ftparchive)"
else
    NEOX_ORIGIN="$ORIGIN" NEOX_LABEL="$LABEL" NEOX_SUITE="$SUITE" \
    NEOX_COMPONENT="$COMPONENT" NEOX_ARCH="$ARCH" NEOX_DESCRIPTION="$DESCRIPTION" \
        python3 "$ROOT/scripts/make-release.py" "$DIST"
fi

# 4) Depo sitesi (HTML/CSS/JS dosyalari repoda kok dizindedir)
cp "$ROOT/index.html" "$ROOT/style.css" "$ROOT/app.js" "$STAGING/"

# 5) Kurulum/guncelleme scriptleri ve site paket listesi
cp "$ROOT/scripts/setup-repo.sh" "$STAGING/setup-repo.sh"
cp "$ROOT/scripts/auto-update.sh" "$STAGING/auto-update.sh"
cp "$ROOT/scripts/neox-repo-auto-update.service" "$STAGING/neox-repo-auto-update.service"
cp "$ROOT/scripts/neox-repo-auto-update.timer" "$STAGING/neox-repo-auto-update.timer"
python3 "$ROOT/scripts/make-packages-json.py" "$STAGING"

echo
echo "==> Derleme tamamlandi: $STAGING"
find "$STAGING" -type f | sort

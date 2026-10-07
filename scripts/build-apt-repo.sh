#!/usr/bin/env bash
# Neox APT deposunu derler.
#
# Yaptiklari:
#   1) pool/ icindeki .deb'leri staging havuzuna kopyalar
#   2) dists/stable/ metadata'sini uretir (Packages, Packages.gz, Release)
#   3) GPG ile imzalar (InRelease + Release.gpg)
#   4) site/ icerigini, anahtarlari ve yardimci scriptleri staging'e kopyalar
#   5) site icin packages.json uretir
#
# Kullanim:  scripts/build-apt-repo.sh [STAGING_DIR]     (varsayilan: public/)
#
# Ortam degiskenleri:
#   NEOX_GPG_KEY_FILE    ozel anahtar dosyasi (armored .asc)
#   NEOX_GPG_PRIVATE_KEY ozel anahtar icerigi (armored) - dosya yoksa bu kullanilir
#   NEOX_GPG_PASSPHRASE  anahtar parolasi (varsa)
#
# Not: gpg yoksa imzalama icin pgpy (python) kullanilir; apt-ftparchive yoksa
#      dpkg-scanpackages + make-release.py kullanilir. CI'da (ubuntu-latest)
#      tum araclar mevcuttur.
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
STAGING="$(cd "$STAGING" && pwd)"   # mutlak yol (cd'den sonra goreceli yol kirlmasin)
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

# 2) Packages indexleri (calisma dizini STAGING; boylece Filename: pool/... seklinde olur)
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

# 3) Release dosyasi
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

# 4) GPG imzalama
KEY_FILE="${NEOX_GPG_KEY_FILE:-}"
if [ -z "$KEY_FILE" ] && [ -n "${NEOX_GPG_PRIVATE_KEY:-}" ]; then
    KEY_FILE="$(mktemp)"
    printf '%s\n' "$NEOX_GPG_PRIVATE_KEY" > "$KEY_FILE"
    chmod 600 "$KEY_FILE"
fi

if [ -z "$KEY_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "HATA: imzalama anahtari bulunamadi (NEOX_GPG_KEY_FILE veya NEOX_GPG_PRIVATE_KEY)" >&2
    exit 1
fi

if command -v gpg >/dev/null 2>&1; then
    export GNUPGHOME
    GNUPGHOME="$(mktemp -d)"
    gpg --batch --import "$KEY_FILE"
    PASSPHRASE_ARGS=()
    if [ -n "${NEOX_GPG_PASSPHRASE:-}" ]; then
        PASSPHRASE_ARGS=(--pinentry-mode loopback --passphrase "$NEOX_GPG_PASSPHRASE")
    fi
    gpg --batch --yes "${PASSPHRASE_ARGS[@]}" \
        --clearsign --output "$DIST/InRelease" "$DIST/Release"
    gpg --batch --yes "${PASSPHRASE_ARGS[@]}" \
        --armor --detach-sign --output "$DIST/Release.gpg" "$DIST/Release"
    echo "==> Release imzalandı (gpg, key: $(gpg --list-secret-keys --with-colons | awk -F: '/^sec/{print $5; exit}'))"
else
    # gpg yoksa pgpy ile imzala; pgpy de yoksa kurmayi dene
    if ! python3 -c "import pgpy" >/dev/null 2>&1; then
        echo "==> pgpy kuruluyor (gpg bulunamadi, imzalama icin gerekli)"
        pip3 install --quiet pgpy \
            || pip3 install --quiet --user pgpy \
            || pip3 install --quiet --break-system-packages pgpy \
            || true
    fi
    if python3 -c "import pgpy" >/dev/null 2>&1; then
        NEOX_GPG_KEY_FILE="$KEY_FILE" python3 "$ROOT/scripts/gpg-sign.py" "$DIST/Release"
    else
        echo "HATA: imzalama icin gpg veya pgpy gerekli" >&2
        exit 1
    fi
fi

# 5) Site icerigi + anahtarlar + yardimci scriptler + packages.json
cp -r "$ROOT/site/." "$STAGING/"
cp "$ROOT/keys/neox-repo-key.asc" "$STAGING/neox-repo-key.asc"

# Binary (dearmored) anahtar - hedef sistemde gpg --dearmor gerektirmez
if command -v gpg >/dev/null 2>&1; then
    gpg --dearmor --yes -o "$STAGING/neox-repo.gpg" "$ROOT/keys/neox-repo-key.asc"
else
    python3 "$ROOT/scripts/dearmor-key.py" "$ROOT/keys/neox-repo-key.asc" "$STAGING/neox-repo.gpg"
fi

cp "$ROOT/scripts/setup-repo.sh" "$STAGING/setup-repo.sh"
cp "$ROOT/scripts/auto-update.sh" "$STAGING/auto-update.sh"
cp "$ROOT/scripts/neox-repo-auto-update.service" "$STAGING/neox-repo-auto-update.service"
cp "$ROOT/scripts/neox-repo-auto-update.timer" "$STAGING/neox-repo-auto-update.timer"
python3 "$ROOT/scripts/make-packages-json.py" "$STAGING"

echo
echo "==> Derleme tamamlandi: $STAGING"
find "$STAGING" -type f | sort

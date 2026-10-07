#!/usr/bin/env bash
# Neox APT deposunu Debian/Ubuntu sistemine ekler.
#
# Kullanim (tek komut):
#   curl -fsSL https://project-neox.github.io/Neox-Repo/setup-repo.sh | sudo bash
#
# veya depo icinden:
#   sudo ./scripts/setup-repo.sh [--enable-auto-update]
#
# --enable-auto-update : otomatik paket guncelleyici systemd timer'ini da kurar.
set -euo pipefail

REPO_URL="${NEOX_REPO_URL:-https://project-neox.github.io/Neox-Repo}"
KEYRING="/usr/share/keyrings/neox-repo.gpg"
SOURCE_LIST="/etc/apt/sources.list.d/neox-repo.list"
SUITE="stable"
COMPONENT="main"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
fi

echo "==> Neox APT deposu ekleniyor: $REPO_URL"

# 1) Imzalama anahtari (binary .gpg - hedef sistemde gpg kurulu olmasa da calisir)
$SUDO mkdir -p /usr/share/keyrings
curl -fsSL "$REPO_URL/neox-repo.gpg" -o /tmp/neox-repo.gpg
$SUDO install -m 0644 /tmp/neox-repo.gpg "$KEYRING"
rm -f /tmp/neox-repo.gpg
echo "    anahtar kuruldu: $KEYRING"

# 2) sources.list.d girdisi
echo "deb [signed-by=$KEYRING] $REPO_URL $SUITE $COMPONENT" | $SUDO tee "$SOURCE_LIST" >/dev/null
echo "    depo girdisi kuruldu: $SOURCE_LIST"

# 3) Paket listelerini guncelle
$SUDO apt-get update
echo "    apt listeleri guncellendi"

# 4) (Opsiyonel) Otomatik guncelleme timer'i
if [ "${1:-}" = "--enable-auto-update" ]; then
    echo "==> Otomatik guncelleme (systemd timer) kuruluyor"
    curl -fsSL "$REPO_URL/auto-update.sh" -o /tmp/neox-repo-auto-update
    $SUDO install -m 0755 /tmp/neox-repo-auto-update /usr/local/bin/neox-repo-auto-update
    rm -f /tmp/neox-repo-auto-update
    for unit in neox-repo-auto-update.service neox-repo-auto-update.timer; do
        curl -fsSL "$REPO_URL/$unit" | $SUDO tee "/etc/systemd/system/$unit" >/dev/null
    done
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now neox-repo-auto-update.timer
    echo "    timer aktif: systemctl list-timers neox-repo-auto-update.timer"
fi

echo
echo "==> Tamam! Depo hazir."
echo "    Paketleri gormek icin : apt-cache search neox"
echo "    Ornek kurulum        : sudo apt install neox-repo-setup"

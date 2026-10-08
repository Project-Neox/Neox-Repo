#!/usr/bin/env bash
# DEOX istemcisini sistemden kaldırır (root gerektirir).
#
# Kullanım:
#   sudo ./uninstall.sh            # istemciyi kaldır (veri korunur)
#   sudo ./uninstall.sh --purge    # istemci + tüm veriler (db, önbellek, config)

set -euo pipefail

PREFIX="/usr/lib/deox"
BIN_DIR="/usr/local/bin"
ETC_DIR="/etc/deox"
PURGE=0

if [[ "${1:-}" == "--purge" ]]; then
    PURGE=1
fi

if [[ $EUID -ne 0 ]]; then
    echo "✗ Bu script root yetkisiyle çalıştırılmalı." >&2
    exit 1
fi

rm -f "$BIN_DIR/deox"
rm -rf "$PREFIX"
rm -f /usr/share/bash-completion/completions/deox
rm -f /usr/share/zsh/site-functions/_deox

if [[ $PURGE -eq 1 ]]; then
    rm -rf "$ETC_DIR" /var/lib/deox /var/cache/deox /var/log/deox.log
    echo "✓ DEOX ve tüm verileri kaldırıldı."
else
    echo "✓ DEOX istemcisi kaldırıldı (veri korunur: /var/lib/deox, $ETC_DIR)."
    echo "  Tüm veriyi silmek için: sudo ./uninstall.sh --purge"
fi

#!/usr/bin/env bash
# DEOX istemcisini sisteme kurar (root gerektirir).
#
# Kullanım:
#   sudo ./install.sh            # /usr/lib/deox + /usr/local/bin/deox
#   sudo ./install.sh --prefix /opt/deox   # özel önek
#
# Kaldırmak için: sudo ./uninstall.sh [--purge]

set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="/usr/lib/deox"
BIN_DIR="/usr/local/bin"
ETC_DIR="/etc/deox"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            PREFIX="$2"
            shift 2
            ;;
        *)
            echo "bilinmeyen seçenek: $1" >&2
            exit 1
            ;;
    esac
done

if [[ $EUID -ne 0 ]]; then
    echo "✗ Bu script root yetkisiyle çalıştırılmalı: sudo ./install.sh" >&2
    exit 1
fi

echo "==> DEOX istemcisi kuruluyor: $PREFIX"

# 1) İstemci kaynakları (src paketi + yapılandırma şablonları)
install -d "$PREFIX" "$BIN_DIR" "$ETC_DIR"
cp -r "$SRC_DIR/src" "$PREFIX/"

# 2) Yapılandırma dosyaları (mevcutsa üzerine yazılmaz)
for f in deox.conf repos.conf; do
    if [[ ! -f "$ETC_DIR/$f" ]]; then
        install -m 644 "$SRC_DIR/config/$f" "$ETC_DIR/$f"
        echo "    yapılandırma kuruldu: $ETC_DIR/$f"
    fi
done

# 3) Çalıştırıcı: /usr/local/bin/deox
cat > "$BIN_DIR/deox" <<EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, "$PREFIX")
from src.main import main
sys.exit(main())
EOF
chmod 755 "$BIN_DIR/deox"

# 4) Hook dizini
install -d "$ETC_DIR/hooks.d"

# 5) Bash/Zsh tab tamamlama
if [[ -d /usr/share/bash-completion/completions ]]; then
    install -m 644 "$SRC_DIR/completions/deox.bash" \
        /usr/share/bash-completion/completions/deox
fi
if [[ -d /usr/share/zsh/site-functions ]]; then
    install -m 644 "$SRC_DIR/completions/deox.zsh" \
        /usr/share/zsh/site-functions/_deox
fi

# 6) Bağımlılıklar (requests/rich) — pip yoksa veya başarısız olursa atlanır
if command -v pip3 >/dev/null 2>&1; then
    echo "==> Python bağımlılıkları kuruluyor (requests, rich)..."
    pip3 install -q -r "$SRC_DIR/requirements.txt" \
        || echo "⚠ bağımlılıklar kurulamadı; deox yine de çalışır (yerleşik yedekler)"
fi

echo
echo "✓ DEOX kuruldu."
echo "  İstemci : $BIN_DIR/deox"
echo "  Config  : $ETC_DIR/deox.conf"
echo "  Hızlı başlangıç:"
echo "    deox -Sy        # depo veritabanını indir"
echo "    deox -Ss htop   # paket ara"
echo "    sudo deox -S htop"

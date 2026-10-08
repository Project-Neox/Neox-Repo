#!/usr/bin/env bash
# Örnek paketleri (deox-hello, deox-libcore) derleyip deoxpool/ içine atar.
#
# Kullanım:
#   ./build.sh              # ../deoxpool dizinine derler
#   ./build.sh /hedef/dir   # özel hedef dizin

set -euo pipefail

cd "$(dirname "$0")"
OUT="${1:-../deoxpool}"
mkdir -p "$OUT"

for pkg in deox-hello deox-libcore; do
    version="$(awk -F': ' '/^Version:/ {print $2}' "$pkg/DEBIAN/control")"
    arch="$(awk -F': ' '/^Architecture:/ {print $2}' "$pkg/DEBIAN/control")"
    deb="$OUT/${pkg}_${version}_${arch}.deb"

    # paket dizininin kendisi içine kopyalamamak için geçici dizin kullan
    # (önceki denemelerden kalan .build kalıntıları da dışarıda tutulur)
    rm -rf "$pkg/.build"
    build_dir="$(mktemp -d)"
    cp -r "$pkg/." "$build_dir/"
    rm -rf "$build_dir/.build"
    find "$build_dir" -type d -exec chmod 755 {} +
    find "$build_dir" -type f -exec chmod 644 {} +
    # çalıştırılabilir dosyaları 755 yap
    find "$build_dir/usr/bin" -type f -exec chmod 755 {} + 2>/dev/null || true

    dpkg-deb --build "$build_dir" "$deb"
    rm -rf "$build_dir"
    echo "✓ $deb"
done

echo
echo "Paketler hazır: $OUT"
echo "Veritabanını yenilemek için (deox-client dizininden):"
echo "  python3 -m src.repo_scanner --pool $OUT --db ../db/deox.db"

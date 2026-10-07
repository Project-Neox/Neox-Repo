#!/usr/bin/env bash
# Derlenmis depoyu uctan uca test eder:
#   1) InRelease + Release.gpg GPG imzalarini gpgv ile dogrular
#   2) depoyu izole bir apt ortaminda file:// kaynagi olarak ekler
#   3) her paketin apt tarafindan gorundugunu ve indirilebildigini dogrular
#
# Kullanim: scripts/selftest-apt-repo.sh [STAGING_DIR]   (varsayilan: public/)
# Not: sistemi etkilemez (tum apt dizinleri gecici klasorde tutulur).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="${1:-$ROOT/public}"
STAGING="$(cd "$STAGING" && pwd)"   # mutlak yola cevir (file:// URI icin)
SUITE="stable"
COMPONENT="main"
ARCH="amd64"
LISTFILE="dists/$SUITE/$COMPONENT/binary-$ARCH/Packages"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "SELFTEST HATA: $*" >&2; exit 1; }

[ -f "$STAGING/$LISTFILE" ] || fail "$LISTFILE yok - once build-apt-repo.sh calistir"
[ -f "$STAGING/dists/$SUITE/InRelease" ] || fail "InRelease yok (imza yok)"
[ -f "$STAGING/dists/$SUITE/Release.gpg" ] || fail "Release.gpg yok (imza yok)"
[ -f "$STAGING/neox-repo-key.asc" ] || fail "neox-repo-key.asc yok"

APT_OPTS=(
    -o "Dir::Etc::sourcelist=$TMP/etc/neox.sources.list"
    -o Dir::Etc::sourceparts=-
    -o "Dir::State::Lists=$TMP/lists"
    -o "Dir::Cache=$TMP/cache"
    -o "Dir::Cache::archives=$TMP/cache/archives"
    -o APT::Get::ListCleanup=0
    -o Debug::NoLocking=1
)

# 1) GPG imzalarini dogrula
if command -v gpg >/dev/null 2>&1; then
    gpg --dearmor --yes -o "$TMP/neox-repo.gpg" "$STAGING/neox-repo-key.asc"
else
    python3 "$ROOT/scripts/dearmor-key.py" "$STAGING/neox-repo-key.asc" "$TMP/neox-repo.gpg"
fi
gpgv --keyring "$TMP/neox-repo.gpg" "$STAGING/dists/$SUITE/InRelease" \
    || fail "InRelease imza dogrulamasi basarisiz"
gpgv --keyring "$TMP/neox-repo.gpg" "$STAGING/dists/$SUITE/Release.gpg" "$STAGING/dists/$SUITE/Release" \
    || fail "Release.gpg imza dogrulamasi basarisiz"
echo "==> GPG imzalari dogrulandi (InRelease + Release.gpg)"

# 2) Depoyu izole apt ortaminda file:// kaynagi olarak ekle
mkdir -p "$TMP/lists/partial" "$TMP/cache/archives/partial" "$TMP/etc"
cat > "$TMP/etc/neox.sources.list" <<EOF
deb [signed-by=$TMP/neox-repo.gpg] file://$STAGING $SUITE $COMPONENT
EOF

if ! UPDATE_OUT="$(apt-get "${APT_OPTS[@]}" update 2>&1)"; then
    fail "apt update basarisiz: $UPDATE_OUT"
fi
# Docker imajlarindaki docker-clean config'i gibi sabit yollu, zararsiz uyarilari gizle
echo "$UPDATE_OUT" | grep -v "cannot remove '/var/cache/apt" || true
echo "==> apt update basarili (imza + checksum dogrulamalari gecti)"

# 3) Her paket: apt tarafindan goruluyor + bu depo kaynagindan indirilebiliyor mu
#    (apt-get download; cozumleme + checksum dogrulamasi + indirme tek adimda)
PKGS="$(awk '/^Package:/{print $2}' "$STAGING/$LISTFILE" | sort -u)"
[ -n "$PKGS" ] || fail "Packages dosyasi bos"
mkdir -p "$TMP/debs"
for p in $PKGS; do
    OUT="$(cd "$TMP/debs" && apt-get "${APT_OPTS[@]}" download "$p" 2>&1)" \
        || fail "$p indirilemedi: $OUT"
    echo "$OUT" | grep -q "$STAGING" \
        || fail "$p: beklenen depo kaynagindan ($STAGING) indirilmedi"
    DEB="$(ls -t "$TMP/debs"/*.deb 2>/dev/null | head -1)"
    [ -n "$DEB" ] || fail "$p: indirilen .deb bulunamadi"
    dpkg-deb --info "$DEB" >/dev/null 2>&1 || fail "$p: indirilen .deb bozuk"
    echo "==> $p: apt cozumledi, depo kaynagindan indirildi, .deb saglam"
done

echo
echo "SELFTEST BASARILI: depo apt tarafindan sorunsuz kullaniliyor"

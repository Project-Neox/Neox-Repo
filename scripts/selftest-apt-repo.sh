#!/usr/bin/env bash
# Derlenmis imzasiz depoyu izole bir apt ortaminda uctan uca test eder:
#   1) Release metadata'sinin var ve GPG imza dosyalarinin yok oldugunu dogrular
#   2) [trusted=yes] kaynagindan apt update calistirir
#   3) her paketin listelendigini ve indirilebildigini dogrular
#
# Kullanim: scripts/selftest-apt-repo.sh [STAGING_DIR] (varsayilan: public/)
# Not: Sistemi etkilemez; apt dizinleri gecici klasorde tutulur.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGING="${1:-$ROOT/public}"
STAGING="$(cd "$STAGING" && pwd)"
SUITE="stable"
COMPONENT="main"
ARCH="amd64"
DIST_DIR="$STAGING/dists/$SUITE"
LISTFILE="$DIST_DIR/$COMPONENT/binary-$ARCH/Packages"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail() { echo "SELFTEST HATA: $*" >&2; exit 1; }

[ -f "$LISTFILE" ] || fail "dists/$SUITE/$COMPONENT/binary-$ARCH/Packages yok - once build-apt-repo.sh calistir"
[ -f "$DIST_DIR/Release" ] || fail "Release metadata'si yok"
[ ! -e "$DIST_DIR/InRelease" ] || fail "InRelease hala uretiliyor; GPG imzasini kaldir"
[ ! -e "$DIST_DIR/Release.gpg" ] || fail "Release.gpg hala uretiliyor; GPG imzasini kaldir"
[ ! -e "$STAGING/neox-repo-key.asc" ] || fail "Eski GPG public key staging'e kopyalanmis"
[ ! -e "$STAGING/neox-repo.gpg" ] || fail "Eski GPG keyring staging'e kopyalanmis"

APT_OPTS=(
    -o "Dir::Etc::sourcelist=$TMP/etc/neox.sources.list"
    -o Dir::Etc::sourceparts=-
    -o "Dir::State::Lists=$TMP/lists"
    -o "Dir::Cache=$TMP/cache"
    -o "Dir::Cache::archives=$TMP/cache/archives"
    -o APT::Get::ListCleanup=0
    -o Debug::NoLocking=1
)

# [trusted=yes] burada acikca imzasiz test deposuna guvenildigini belirtir.
mkdir -p "$TMP/lists/partial" "$TMP/cache/archives/partial" "$TMP/etc"
cat > "$TMP/etc/neox.sources.list" <<EOF
deb [trusted=yes] file://$STAGING $SUITE $COMPONENT
EOF

if ! UPDATE_OUT="$(apt-get "${APT_OPTS[@]}" update 2>&1)"; then
    fail "apt update basarisiz: $UPDATE_OUT"
fi
# Docker imajlarindaki sabit yollu, zararsiz apt-clean uyarilarini gizle.
printf '%s\n' "$UPDATE_OUT" | grep -v "cannot remove '/var/cache/apt" || true
echo "==> apt update basarili (imzasiz depo, metadata checksum kontrolu)"

# Her paket: apt listesinde gorunuyor, bu yerel depodan indiriliyor ve saglam.
mapfile -t PKGS < <(awk '/^Package:/{print $2}' "$LISTFILE" | sort -u)
[ "${#PKGS[@]}" -gt 0 ] || fail "Packages dosyasi bos"
mkdir -p "$TMP/debs"
for PACKAGE in "${PKGS[@]}"; do
    if ! OUT="$(cd "$TMP/debs" && apt-get "${APT_OPTS[@]}" download "$PACKAGE" 2>&1)"; then
        fail "$PACKAGE indirilemedi: $OUT"
    fi
    if ! grep -Fq "$STAGING" <<< "$OUT"; then
        fail "$PACKAGE beklenen depo kaynagindan ($STAGING) indirilmedi: $OUT"
    fi
    DEB="$(ls -t "$TMP/debs"/*.deb 2>/dev/null | head -1 || true)"
    [ -n "$DEB" ] || fail "$PACKAGE: indirilen .deb bulunamadi"
    dpkg-deb --info "$DEB" >/dev/null 2>&1 || fail "$PACKAGE: indirilen .deb bozuk"
    echo "==> $PACKAGE: apt ile depodan indirildi, .deb saglam"
done

echo
echo "SELFTEST BASARILI: imzasiz depo apt tarafindan kullanilabiliyor"

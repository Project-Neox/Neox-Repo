#!/usr/bin/env bash
# Neox APT deposundaki paketleri otomatik kurar/gunceller.
#
# Depoya yeni bir .deb yayinlandiginda bu script:
#   1) sadece Neox deposunun listesini yeniler (tum sistemi apt update'le yormaz)
#   2) depodaki tum paketleri kurar (yeni paketler otomatik sisteme gecer,
#      kurulu olanlar guncellenir)
#
# Zamanlanmis calistirmak icin systemd timer veya cron kullanin:
#   scripts/neox-repo-auto-update.timer  (systemd, onerilen)
#   veya crontab:  17 * * * *  /usr/local/bin/neox-repo-auto-update
set -euo pipefail

SOURCE_LIST="/etc/apt/sources.list.d/neox-repo.list"

if [ ! -f "$SOURCE_LIST" ]; then
    echo "HATA: $SOURCE_LIST bulunamadi. Once 'neox-repo-setup' ile depoyu ekle." >&2
    exit 1
fi

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
fi

echo "==> Neox deposu listesi yenileniyor (sadece bu depo)..."
$SUDO apt-get update \
    -o Dir::Etc::sourcelist="$SOURCE_LIST" \
    -o Dir::Etc::sourceparts=- \
    -o APT::Get::ListCleanup=0 \
    -o Debug::NoLocking=1

# Repodaki tum paketleri bul (apt liste dosyalarindan)
mapfile -t PKGS < <(awk '/^Package:/{print $2}' /var/lib/apt/lists/*Neox-Repo*Packages 2>/dev/null | sort -u)

if [ "${#PKGS[@]}" -eq 0 ]; then
    echo "==> Neox deposunda paket bulunamadi, islem yok."
    exit 0
fi

echo "==> Kurulacak/guncellenecek paketler: ${PKGS[*]}"
$SUDO apt-get install -y "${PKGS[@]}"

echo "==> Neox deposu guncellemesi tamamlandi."

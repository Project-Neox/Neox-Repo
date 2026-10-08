# -*- coding: utf-8 -*-
"""
DEOX güvenlik modülü.

- İndirilen her dosyanın SHA256 (ve varsa MD5) checksum kontrolü
- .deb dosya bütünlüğü kontrolü (ar arşivi + dpkg-deb --info)
- Uyuşmazlıkta otomatik tekrar indirme (RETRY_LIMIT denemesi, downloader'da)
"""

import hashlib
import os

_CHUNK = 1024 * 1024  # 1 MB'lik parçalarla okuma

# Checksum uyuşmazlığında yapılacak toplam indirme denemesi
RETRY_LIMIT = 3


def sha256_file(path):
    """Dosyanın SHA256 özetini (hex) hesaplar."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path):
    """Dosyanın MD5 özetini (hex) hesaplar."""
    digest = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums(path, sha256=None, md5=None):
    """
    İndirilen dosyanın checksum'larını doğrular.
    Dönüş: (ok: bool, mesaj: str)
    """
    if sha256:
        actual = sha256_file(path)
        if actual.lower() != str(sha256).lower():
            return False, ("SHA256 uyuşmazlığı: beklenen %s, bulunan %s"
                           % (sha256, actual))
    if md5:
        actual = md5_file(path)
        if actual.lower() != str(md5).lower():
            return False, ("MD5 uyuşmazlığı: beklenen %s, bulunan %s"
                           % (md5, actual))
    return True, "checksum doğrulandı"


def verify_deb(path):
    """
    .deb dosyasının bütünlüğünü kontrol eder.
    Dönüş: (ok: bool, mesaj: str)
    """
    from . import utils  # döngüsel import'u önlemek için yerel import

    if not os.path.isfile(path):
        return False, "dosya bulunamadı: %s" % path
    # .deb dosyaları 'ar' arşividir; sihir baytları kontrol edilir
    with open(path, "rb") as f:
        if f.read(8) != b"!<arch>\n":
            return False, "geçersiz .deb dosyası (ar arşivi değil)"
    rc, out, err = utils.run_cmd(["dpkg-deb", "--info", path])
    if rc != 0:
        detail = (err.strip() or out.strip() or "bilinmeyen hata")
        return False, "bozuk .deb: %s" % detail
    return True, "deb bütünlüğü doğrulandı"

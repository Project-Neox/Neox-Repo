# -*- coding: utf-8 -*-
"""
DEOX önbellek yönetimi.

Önbellek kökü: /var/cache/deox/  (yapılandırmayla değiştirilebilir)
  └── pkg/          indirilen .deb dosyaları
      ve *.part     kaldığı yerden devam eden yarı indirmeler

- deox -Sc   : .part dosyalarını ve CLEAN_OLDER_THAN_DAYS'den eski .deb'leri siler
- deox -Scc  : tüm önbelleği siler
"""

import os
import time

from . import utils

PART_SUFFIX = ".part"
CLEAN_OLDER_THAN_DAYS = 30  # -Sc'nin "eski" saydığı yaş (gün)


class CacheManager:
    """/var/cache/deox önbelleğini yönetir."""

    def __init__(self, cache_dir=None):
        self.root = cache_dir or utils.root_path("/var/cache/deox")
        self.pkg_dir = os.path.join(self.root, "pkg")

    def ensure(self):
        """Önbellek dizinlerini oluşturur."""
        utils.ensure_dir(self.pkg_dir)
        return self

    def path_for(self, filename):
        """Dosya adı için önbellek yolunu döndürür (güvenli ad)."""
        return os.path.join(self.pkg_dir, os.path.basename(filename))

    def exists(self, filename):
        """Dosya önbellekte var mı?"""
        path = self.path_for(filename)
        return os.path.isfile(path) and not path.endswith(PART_SUFFIX)

    def add(self, src_path, filename):
        """İndirilmiş dosyayı önbelleğe taşır."""
        self.ensure()
        import shutil
        dst = self.path_for(filename)
        shutil.move(src_path, dst)
        return dst

    def list(self):
        """Önbellekteki dosya adlarını listeler."""
        self.ensure()
        return sorted(os.listdir(self.pkg_dir))

    def size(self):
        """Önbelleğin toplam boyutu (bayt)."""
        total = 0
        for root, _dirs, files in os.walk(self.root):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
        return total

    def clean(self, all_files=False):
        """
        Önbelleği temizler.

        all_files=False → -Sc : .part dosyaları + CLEAN_OLDER_THAN_DAYS'den eski
        all_files=True  → -Scc: tüm önbellek
        Dönüş: {"removed": int, "freed_bytes": int}
        """
        removed = 0
        freed = 0
        cutoff = time.time() - CLEAN_OLDER_THAN_DAYS * 86400
        for root, _dirs, files in os.walk(self.root):
            for name in files:
                path = os.path.join(root, name)
                try:
                    stat = os.stat(path)
                    if (all_files or name.endswith(PART_SUFFIX)
                            or stat.st_mtime < cutoff):
                        freed += stat.st_size
                        os.remove(path)
                        removed += 1
                except OSError:
                    pass
        # boş kalan dizinleri temizle
        for root, dirs, _files in os.walk(self.root, topdown=False):
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
        return {"removed": removed, "freed_bytes": freed}

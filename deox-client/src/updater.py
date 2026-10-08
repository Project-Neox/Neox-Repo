# -*- coding: utf-8 -*-
"""
DEOX güncelleme modülü.

- sync          : tüm etkin depolardan db/deox.db indirilip yerel sync
                  veritabanına işlenir (çoklu depo birleştirilir)
- check_updates : kurulu paketler için güncelleme kontrolü (deox -Su öncesi)

Paket güncelleme akışı (indirme + kurulum) main.py içindeki cmd_install ile
ortaktır; bu modül yalnızca veri katmanını yönetir.
"""

import sqlite3
import tempfile

from . import downloader as dl
from . import ui
from . import utils
from .database import Database
from .resolver import Resolver


class Updater:
    """Depo senkronizasyonu ve güncelleme kontrolü."""

    def __init__(self, config, paths, sync_db, local_db, cache, downloader):
        self.config = config
        self.paths = paths
        self.sync_db = sync_db
        self.local_db = local_db
        self.cache = cache
        self.downloader = downloader

    def sync(self, force=False):
        """
        Tüm etkin depoları senkronize eder.

        Her depo için <server>/db/deox.db indirilir, geçerliliği denetlenir ve
        içindeki paketler yerel sync veritabanına işlenir (çoklu depo desteği:
        her deponun paketleri kendi adıyla eklenir, öncelik sırasına göre).
        Depo listesi yapılandırma dosyalarından (deox.conf / repos.conf)
        ve yerel veritabanındaki kayıtlardan birleştirilir.

        Dönüş: özet sözlüğü
        """
        # yapılandırma dosyalarındaki depoları veritabanına işle
        config_repos = utils.load_repos(self.config)
        for repo in config_repos:
            self.local_db.upsert_repo(repo["name"], repo["server"],
                                      repo["enabled"], repo["priority"])
            # GUI'nin sync db üzerinden de okuyabilmesi için oraya da yaz
            self.sync_db.upsert_repo(repo["name"], repo["server"],
                                     repo["enabled"], repo["priority"])

        repos = self.local_db.list_repos()
        if not repos:
            raise utils.DeoxError(
                "tanımlı depo yok. 'deox --add-repo <isim> <url>' ile ekleyin.")

        summary = {"repos": [], "packages": 0, "force": force}
        for repo in repos:
            if not repo["enabled"]:
                ui.info("%s deposu devre dışı, atlanıyor." % repo["name"])
                continue
            ui.info("%s senkronize ediliyor..." % ui.pkg(repo["name"]))
            url = repo["url"].rstrip("/") + "/db/deox.db"
            with tempfile.TemporaryDirectory() as tmp:
                item = dl.DownloadItem(repo["name"], url, tmp, "deox.db")
                try:
                    # db dosyasının checksum'ı bilinmediğinden düz indirme
                    path = self.downloader.download(item)
                except dl.DownloadError as exc:
                    ui.error("%s indirilemedi: %s" % (repo["name"], exc))
                    summary["repos"].append(
                        {"name": repo["name"], "ok": False, "error": str(exc)})
                    continue
                if not Database.is_valid(path):
                    ui.error("%s veritabanı geçersiz, atlanıyor."
                             % repo["name"])
                    summary["repos"].append(
                        {"name": repo["name"], "ok": False,
                         "error": "geçersiz veritabanı"})
                    continue
                count = self._import_repo_db(path, repo["name"])

            self.local_db.touch_repo(repo["name"])
            summary["repos"].append(
                {"name": repo["name"], "ok": True, "packages": count})
            summary["packages"] += count
            ui.success("%s: %d paket" % (repo["name"], count))
        return summary

    def _import_repo_db(self, src_path, repo_name):
        """
        İndirilen depo veritabanındaki paketleri sync veritabanına işler.
        Dönüş: işlenen paket sayısı.
        """
        try:
            src = sqlite3.connect(src_path)
            src.row_factory = sqlite3.Row
            tables = {r[0] for r in src.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "packages" not in tables:
                return 0
            packages = [dict(r) for r in src.execute("SELECT * FROM packages")]
            deps_by_name = {}
            if "dependencies" in tables:
                id2name = {p["id"]: p["name"] for p in packages}
                for row in src.execute("SELECT * FROM dependencies"):
                    dep = dict(row)
                    name = id2name.get(dep.get("package_id"))
                    if name:
                        deps_by_name.setdefault(name, []).append(dep)
            src.close()
        except sqlite3.Error as exc:
            raise utils.DeoxError(
                "%s veritabanı okunamadı: %s" % (repo_name, exc))

        self.sync_db.replace_repo_packages(repo_name, packages, deps_by_name)
        return len(packages)

    def check_updates(self):
        """Kurulu paketler için güncelleme listesini döndürür."""
        return Resolver(self.sync_db, self.local_db,
                        self.config.architecture).find_upgrades()

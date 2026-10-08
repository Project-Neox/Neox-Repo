# -*- coding: utf-8 -*-
"""
DEOX SQLite veritabanı modülü.

İki veritabanı vardır:
  - Uzak (sync)  : /var/lib/deox/sync/deox.db   → repolardaki tüm paketler
  - Yerel (local): /var/lib/deox/local/deox.db  → kurulu paketler, geçmiş, depolar

İkisi de AYNI şemayı kullanır; bu sayede ileride yapılacak GUI uygulaması
iki veritabanını da doğrudan okuyabilir. Tüm komutlar --json ile JSON
çıktısı üretebildiğinden, bu katman GUI için veri kaynağıdır.
"""

import json
import os
import sqlite3
from contextlib import closing

from . import utils

# Ortak şema — sync ve local veritabanlarında aynen oluşturulur.
SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT NOT NULL UNIQUE,
    version          TEXT NOT NULL,
    release          INTEGER DEFAULT 1,
    architecture     TEXT NOT NULL,          -- "amd64", "arm64", "all"
    description      TEXT,
    long_description TEXT,
    maintainer       TEXT,
    homepage         TEXT,
    license          TEXT,
    section          TEXT,                   -- kategori
    priority         TEXT DEFAULT 'optional',
    filename         TEXT NOT NULL,          -- deoxpool/ içindeki dosya adı
    size             INTEGER,                -- .deb boyutu (bayt)
    installed_size   INTEGER,                -- kurulu boyut (bayt)
    sha256           TEXT NOT NULL,
    md5sum           TEXT,
    upload_date      DATETIME DEFAULT CURRENT_TIMESTAMP,
    download_count   INTEGER DEFAULT 0,
    votes            INTEGER DEFAULT 0,
    flagged          BOOLEAN DEFAULT 0,
    repo             TEXT DEFAULT 'deox'     -- çoklu depo desteği için eklendi
);

CREATE TABLE IF NOT EXISTS dependencies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id   INTEGER REFERENCES packages(id) ON DELETE CASCADE,
    dep_name     TEXT NOT NULL,               -- örn. "libc6 (>= 2.34)" veya "a | b"
    dep_version  TEXT,
    dep_type     TEXT NOT NULL                 -- "depends", "conflicts",
                                              -- "replaces", "provides",
                                              -- "recommends", "suggests"
);

CREATE TABLE IF NOT EXISTS installed (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id     INTEGER REFERENCES packages(id),
    name           TEXT NOT NULL UNIQUE,
    version        TEXT NOT NULL,
    install_date   DATETIME DEFAULT CURRENT_TIMESTAMP,
    install_reason TEXT DEFAULT 'explicit',    -- "explicit" veya "dependency"
    files          TEXT                       -- JSON array
);

CREATE TABLE IF NOT EXISTS repositories (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL UNIQUE,
    url       TEXT NOT NULL,
    enabled   BOOLEAN DEFAULT 1,
    priority  INTEGER DEFAULT 100,
    last_sync DATETIME
);

CREATE TABLE IF NOT EXISTS history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    action       TEXT NOT NULL,                -- "install", "remove", "update"
    package_name TEXT NOT NULL,
    from_version TEXT,
    to_version   TEXT,
    timestamp    DATETIME DEFAULT CURRENT_TIMESTAMP,
    success      BOOLEAN DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_deps_pkg ON dependencies(package_id);
CREATE INDEX IF NOT EXISTS idx_deps_name ON dependencies(dep_name);
CREATE INDEX IF NOT EXISTS idx_installed_name ON installed(name);
CREATE INDEX IF NOT EXISTS idx_history_ts ON history(timestamp);
"""


class Database:
    """Tek bir deox.db dosyası üzerindeki tüm işlemler."""

    def __init__(self, path):
        self.path = path
        utils.ensure_dir(os.path.dirname(path))
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self):
        """Her işlem için yeni bağlantı (thread-safe ve basit)."""
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def is_valid(path):
        """Dosyanın geçerli bir deox veritabanı olup olmadığını denetler."""
        try:
            conn = sqlite3.connect(path)
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            conn.close()
            return "packages" in tables
        except sqlite3.Error:
            return False

    def integrity(self):
        """PRAGMA integrity_check sonucu."""
        try:
            with closing(self._connect()) as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                return bool(row) and row[0] == "ok"
        except sqlite3.Error:
            return False

    # ------------------------------------------------------------------
    # Paketler
    # ------------------------------------------------------------------

    def upsert_package(self, pkg, dependencies=None):
        """Tek bir paketi ekler/günceller (isim unique)."""
        with closing(self._connect()) as conn:
            cur = conn.execute(
                """INSERT INTO packages
                   (name, version, release, architecture, description,
                    long_description, maintainer, homepage, license, section,
                    priority, filename, size, installed_size, sha256, md5sum,
                    upload_date, download_count, votes, flagged, repo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                           COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     version=excluded.version, release=excluded.release,
                     architecture=excluded.architecture,
                     description=excluded.description,
                     long_description=excluded.long_description,
                     maintainer=excluded.maintainer, homepage=excluded.homepage,
                     license=excluded.license, section=excluded.section,
                     priority=excluded.priority, filename=excluded.filename,
                     size=excluded.size, installed_size=excluded.installed_size,
                     sha256=excluded.sha256, md5sum=excluded.md5sum,
                     upload_date=excluded.upload_date, repo=excluded.repo""",
                (pkg["name"], pkg.get("version"), pkg.get("release", 1),
                 pkg.get("architecture", "all"), pkg.get("description"),
                 pkg.get("long_description"), pkg.get("maintainer"),
                 pkg.get("homepage"), pkg.get("license"), pkg.get("section"),
                 pkg.get("priority", "optional"), pkg.get("filename"),
                 pkg.get("size"), pkg.get("installed_size"), pkg.get("sha256"),
                 pkg.get("md5sum"), pkg.get("upload_date"),
                 pkg.get("download_count", 0), pkg.get("votes", 0),
                 pkg.get("flagged", 0), pkg.get("repo", "deox")))
            pid = cur.lastrowid
            for dep in dependencies or []:
                conn.execute(
                    "INSERT INTO dependencies (package_id, dep_name, dep_version, dep_type)"
                    " VALUES (?, ?, ?, ?)",
                    (pid, dep["dep_name"], dep.get("dep_version"), dep["dep_type"]))
            conn.commit()
            return pid

    def replace_repo_packages(self, repo, packages, deps_by_name, preserve=True):
        """
        Bir deponun tüm paketlerini veritabanına işler (sync işlemi).

        Deponun eski paketleri silinir, yenileri eklenir. preserve=True ise
        oy/indirme-sayısı/işaret bilgileri paket adıyla taşınır.
        """
        with closing(self._connect()) as conn:
            old_stats = {}
            if preserve:
                for row in conn.execute(
                        "SELECT name, votes, flagged, download_count"
                        " FROM packages WHERE repo = ?", (repo,)):
                    old_stats[row["name"]] = dict(row)
            conn.execute("DELETE FROM packages WHERE repo = ?", (repo,))
            for pkg in packages:
                stats = old_stats.get(pkg["name"], {})
                cur = conn.execute(
                    """INSERT INTO packages
                       (name, version, release, architecture, description,
                        long_description, maintainer, homepage, license, section,
                        priority, filename, size, installed_size, sha256, md5sum,
                        upload_date, download_count, votes, flagged, repo)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                               COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?)""",
                    (pkg["name"], pkg.get("version"), pkg.get("release", 1),
                     pkg.get("architecture", "all"), pkg.get("description"),
                     pkg.get("long_description"), pkg.get("maintainer"),
                     pkg.get("homepage"), pkg.get("license"), pkg.get("section"),
                     pkg.get("priority", "optional"), pkg.get("filename"),
                     pkg.get("size"), pkg.get("installed_size"), pkg.get("sha256"),
                     pkg.get("md5sum"), pkg.get("upload_date"),
                     stats.get("download_count", 0), stats.get("votes", 0),
                     stats.get("flagged", 0), repo))
                pid = cur.lastrowid
                for dep in deps_by_name.get(pkg["name"], []):
                    conn.execute(
                        "INSERT INTO dependencies"
                        " (package_id, dep_name, dep_version, dep_type)"
                        " VALUES (?, ?, ?, ?)",
                        (pid, dep["dep_name"], dep.get("dep_version"),
                         dep["dep_type"]))
            conn.commit()

    def get_package(self, name):
        """Ada göre paket kaydını döndürür (yoksa None)."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM packages WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None

    def search(self, keyword, limit=50):
        """Ad veya açıklamada anahtar kelime arar."""
        like = "%%%s%%" % keyword
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(
                """SELECT * FROM packages
                   WHERE name LIKE ? OR description LIKE ?
                   ORDER BY name LIMIT ?""", (like, like, limit))]

    def list_packages(self, repo=None):
        """Tüm paketleri (veya bir deponunkileri) listeler."""
        with closing(self._connect()) as conn:
            if repo:
                rows = conn.execute(
                    "SELECT * FROM packages WHERE repo = ? ORDER BY name",
                    (repo,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM packages ORDER BY name").fetchall()
            return [dict(r) for r in rows]

    def count_packages(self, repo=None):
        """Paket sayısını döndürür."""
        with closing(self._connect()) as conn:
            if repo:
                return conn.execute(
                    "SELECT COUNT(*) FROM packages WHERE repo = ?",
                    (repo,)).fetchone()[0]
            return conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]

    def record_download(self, name):
        """Paketin indirme sayacını bir artırır."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE packages SET download_count = download_count + 1"
                " WHERE name = ?", (name,))
            conn.commit()

    def vote(self, name, delta=1):
        """Paketin oy sayısını artırır/azaltır."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE packages SET votes = votes + ? WHERE name = ?",
                (delta, name))
            conn.commit()

    def flag(self, name):
        """Paketi işaretli (flagged) olarak işaretler."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE packages SET flagged = 1 WHERE name = ?", (name,))
            conn.commit()

    def recent(self, limit=10):
        """Son eklenen paketler."""
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM packages ORDER BY upload_date DESC, id DESC LIMIT ?",
                (limit,))]

    def top_downloads(self, limit=10):
        """En çok indirilen paketler."""
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM packages ORDER BY download_count DESC, id DESC LIMIT ?",
                (limit,))]

    def stats(self):
        """Genel istatistik sözlüğü."""
        with closing(self._connect()) as conn:
            def one(sql):
                return conn.execute(sql).fetchone()[0]
            return {
                "packages": one("SELECT COUNT(*) FROM packages"),
                "dependencies": one("SELECT COUNT(*) FROM dependencies"),
                "repositories": one("SELECT COUNT(*) FROM repositories"),
                "total_downloads": one(
                    "SELECT COALESCE(SUM(download_count), 0) FROM packages"),
                "total_votes": one(
                    "SELECT COALESCE(SUM(votes), 0) FROM packages"),
                "flagged": one(
                    "SELECT COUNT(*) FROM packages WHERE flagged = 1"),
            }

    # ------------------------------------------------------------------
    # Bağımlılıklar
    # ------------------------------------------------------------------

    def deps_of(self, name, dep_type=None):
        """Bir paketin bağımlılık kayıtlarını döndürür."""
        sql = ("SELECT d.* FROM dependencies d"
               " JOIN packages p ON p.id = d.package_id WHERE p.name = ?")
        params = [name]
        if dep_type:
            sql += " AND d.dep_type = ?"
            params.append(dep_type)
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(sql, params)]

    def providers_of(self, name):
        """Bir sanal paketi 'provides' eden paketleri döndürür."""
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(
                """SELECT p.* FROM packages p
                   JOIN dependencies d ON d.package_id = p.id
                   WHERE d.dep_type = 'provides' AND d.dep_name = ?""",
                (name,))]

    # ------------------------------------------------------------------
    # Kurulu paketler (yerel)
    # ------------------------------------------------------------------

    def add_installed(self, name, version, package_id=None, reason="explicit",
                      files=None):
        """Kurulu paket kaydı ekler/günceller."""
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO installed
                   (package_id, name, version, install_reason, files)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     version=excluded.version,
                     package_id=excluded.package_id,
                     install_reason=excluded.install_reason,
                     files=excluded.files,
                     install_date=CURRENT_TIMESTAMP""",
                (package_id, name, version, reason,
                 json.dumps(files or [], ensure_ascii=False)))
            conn.commit()

    def remove_installed(self, name):
        """Kurulu paket kaydını siler."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM installed WHERE name = ?", (name,))
            conn.commit()

    def get_installed(self, name=None):
        """Kurulu paket(ler)i döndürür; name verilirse tek sözlük."""
        with closing(self._connect()) as conn:
            if name:
                row = conn.execute(
                    "SELECT * FROM installed WHERE name = ?", (name,)).fetchone()
                return dict(row) if row else None
            return [dict(r) for r in conn.execute(
                "SELECT * FROM installed ORDER BY name")]

    def is_installed(self, name):
        """Paket yerel veritabanında kurulu mu?"""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM installed WHERE name = ?", (name,)).fetchone()
            return row is not None

    def set_install_reason(self, name, reason):
        """Kurulum nedenini günceller ('explicit' / 'dependency')."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE installed SET install_reason = ? WHERE name = ?",
                (reason, name))
            conn.commit()

    def installed_count(self):
        """Kurulu paket sayısı."""
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM installed").fetchone()[0]

    # ------------------------------------------------------------------
    # Geçmiş
    # ------------------------------------------------------------------

    def add_history(self, action, package_name, from_version=None,
                    to_version=None, success=True):
        """İşlem geçmişine kayıt ekler."""
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO history"
                " (action, package_name, from_version, to_version, success)"
                " VALUES (?, ?, ?, ?, ?)",
                (action, package_name, from_version, to_version,
                 1 if success else 0))
            conn.commit()

    def get_history(self, limit=50):
        """Geçmiş kayıtlarını (yeniden eskiye) döndürür."""
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))]

    def get_history_entry(self, history_id):
        """Tek bir geçmiş kaydını döndürür."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM history WHERE id = ?", (history_id,)).fetchone()
            return dict(row) if row else None

    def history_count(self):
        """Geçmiş kayıt sayısı."""
        with closing(self._connect()) as conn:
            return conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]

    # ------------------------------------------------------------------
    # Depolar
    # ------------------------------------------------------------------

    def upsert_repo(self, name, url, enabled=True, priority=100):
        """Depo kaydı ekler/günceller."""
        with closing(self._connect()) as conn:
            conn.execute(
                """INSERT INTO repositories (name, url, enabled, priority)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     url=excluded.url, enabled=excluded.enabled,
                     priority=excluded.priority""",
                (name, url, 1 if enabled else 0, priority))
            conn.commit()

    def remove_repo(self, name):
        """Depo kaydını siler."""
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM repositories WHERE name = ?", (name,))
            conn.commit()

    def list_repos(self):
        """Tüm depo kayıtlarını döndürür."""
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM repositories ORDER BY priority, name")]

    def get_repo(self, name):
        """Ada göre depo kaydını döndürür."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM repositories WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None

    def touch_repo(self, name, when=None):
        """Deponun son senkronizasyon zamanını günceller."""
        with closing(self._connect()) as conn:
            conn.execute(
                "UPDATE repositories SET last_sync = ? WHERE name = ?",
                (when or utils.now_str(), name))
            conn.commit()

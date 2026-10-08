# -*- coding: utf-8 -*-
"""
DEOX repo tarayıcı (repo sahibi için).

deoxpool/ altındaki tüm .deb dosyalarını tarar:
  - dpkg-deb ile metadata çıkarır (Package, Version, Depends vb.)
  - SHA256/MD5 checksum ve boyut hesaplar
  - db/deox.db SQLite veritabanına yazar

Bu db dosyası repo'ya commit edilir; istemciler `deox -Sy` ile indirir.

Kullanım (deox-client dizininden):
    python3 -m src.repo_scanner --pool ../deox-repo/deoxpool --db ../deox-repo/db/deox.db

veya doğrudan:
    python3 src/repo_scanner.py --pool ../deox-repo/deoxpool --db ../deox-repo/db/deox.db

Oy/indirme-sayısı/işaret bilgileri yeniden taramada paket adıyla taşınır.
"""

import argparse
import glob
import os
import sys

try:
    from . import security, utils
    from .database import Database
except ImportError:  # doğrudan script olarak çalıştırılırsa
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from src import security, utils
    from src.database import Database

# dpkg-deb ile okunacak kontrol alanları → (db alanı, dep_type)
DEP_FIELDS = (
    ("Depends", "depends"),
    ("Recommends", "recommends"),
    ("Suggests", "suggests"),
    ("Conflicts", "conflicts"),
    ("Replaces", "replaces"),
    ("Provides", "provides"),
)


def scan_deb(path):
    """
    Bir .deb dosyasından (paket sözlüğü, bağımlılık listesi) üretir.
    Metadata okunamazsa None döner.
    """
    rc, out, _err = utils.run_cmd(["dpkg-deb", "-f", path])
    if rc != 0:
        return None
    control = utils.parse_control(out)

    name = control.get("Package")
    if not name:
        return None
    version = control.get("Version", "")
    _epoch, _upstream, revision = utils.split_version(version)
    try:
        release = int(revision) if revision else 1
    except ValueError:
        release = 1

    # Description: ilk satır özet, gerisi uzun açıklama
    desc_lines = (control.get("Description") or "").splitlines()
    synopsis = desc_lines[0].strip() if desc_lines else ""
    long_desc = "\n".join(l.strip() for l in desc_lines[1:] if l.strip()) or None

    # Installed-Size KiB cinsindendir → bayta çevrilir
    installed_size = None
    if control.get("Installed-Size"):
        try:
            installed_size = int(control["Installed-Size"]) * 1024
        except ValueError:
            pass

    # Bağımlılıklar: her virgül grubu tek satır; grup içindeki
    # alternatifler "a | b" biçiminde korunur (çözücü ayrıştırır).
    deps = []
    for field, dep_type in DEP_FIELDS:
        raw = control.get(field)
        if not raw:
            continue
        for group in raw.split(","):
            group = " ".join(group.split())
            if not group:
                continue
            alternatives = utils.parse_depends(group)
            if len(alternatives) == 1 and len(alternatives[0]) == 1:
                dep_name, _op, dep_version = alternatives[0][0]
                # tek alternatif: kısıt varsa dep_version'a yazılır
                # (görüntüleme için; çözücü asıl kısıtı dep_name'den okur)
                deps.append({"dep_name": group, "dep_version": dep_version,
                             "dep_type": dep_type})
            else:
                deps.append({"dep_name": group, "dep_version": None,
                             "dep_type": dep_type})

    pkg = {
        "name": name,
        "version": version,
        "release": release,
        "architecture": control.get("Architecture", "all"),
        "description": synopsis,
        "long_description": long_desc,
        "maintainer": control.get("Maintainer"),
        "homepage": control.get("Homepage"),
        "license": control.get("License"),
        "section": control.get("Section"),
        "priority": control.get("Priority", "optional"),
        "filename": os.path.basename(path),
        "size": os.path.getsize(path),
        "installed_size": installed_size,
        "sha256": security.sha256_file(path),
        "md5sum": security.md5_file(path),
    }
    return pkg, deps


def scan_pool(pool_dir, db_path, repo_name="deox"):
    """
    deoxpool dizinindeki tüm .deb'leri tarayıp veritabanına yazar.
    Dönüş: özet sözlüğü
    """
    debs = sorted(glob.glob(os.path.join(pool_dir, "*.deb")))
    db = Database(db_path)
    packages = []
    deps_by_name = {}
    skipped = []

    for path in debs:
        result = scan_deb(path)
        if result is None:
            skipped.append(os.path.basename(path))
            print("✗ atlanıyor (metadata okunamadı): %s" % os.path.basename(path))
            continue
        pkg, deps = result
        pkg["repo"] = repo_name
        packages.append(pkg)
        deps_by_name[pkg["name"]] = deps
        print("✓ %s %s (%s) — %s, %d bağımlılık"
              % (pkg["name"], pkg["version"], pkg["architecture"],
                 utils.format_size(pkg["size"]), len(deps)))

    if not packages:
        print("⚠ %s içinde işlenebilir .deb bulunamadı." % pool_dir)

    # oy/indirme/işaret bilgileri korunarak depoyu yenile
    db.replace_repo_packages(repo_name, packages, deps_by_name, preserve=True)
    return {"scanned": len(packages), "skipped": skipped,
            "db": db_path, "repo": repo_name}


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="repo_scanner",
        description="DEOX repo tarayıcı: deoxpool/*.deb → db/deox.db")
    parser.add_argument("--pool", default="deoxpool",
                        help=".deb havuzu dizini (varsayılan: deoxpool)")
    parser.add_argument("--db", default="db/deox.db",
                        help="hedef SQLite veritabanı (varsayılan: db/deox.db)")
    parser.add_argument("--repo", default="deox",
                        help="depo adı — packages.repo (varsayılan: deox)")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.pool):
        print("hata: %s dizini bulunamadı" % args.pool, file=sys.stderr)
        return 1

    print("🔮 DEOX repo tarayıcı — havuz: %s" % args.pool)
    summary = scan_pool(args.pool, args.db, args.repo)
    print("\nToplam %d paket işlendi → %s" % (summary["scanned"], summary["db"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
DEOX repo tarayıcı (repo sahibi için).

deoxpool/ altındaki .deb dosyalarını dosya adlarından indeksler:
  - Paket adı, sürümü ve mimari <paket>_<sürüm>_<mimari>.deb biçiminden alınır
  - .deb içindeki kontrol alanları varsa açıklama/bağımlılık gibi ek bilgiler okunur
  - SHA256/MD5 checksum ve boyut hesaplanır (Git LFS pointer'ları da desteklenir)
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
import re
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

_PACKAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
_ARCHITECTURE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_LFS_VERSION = "version https://git-lfs.github.com/spec/v1"
_LFS_OID_RE = re.compile(r"^oid sha256:([0-9a-fA-F]{64})$")
_LFS_SIZE_RE = re.compile(r"^size ([0-9]+)$")


def parse_deb_filename(path):
    """Dosya adından (paket adı, sürüm, mimari) bilgisini alır.

    Beklenen adlandırma: ``<paket>_<sürüm>_<mimari>.deb``. Paket adı ve
    mimari Debian paket adı biçimine uygun olmalıdır. Hatalı adlarda None döner.
    """
    filename = os.path.basename(path)
    if not filename.endswith(".deb"):
        return None

    parts = filename[:-4].rsplit("_", 2)
    if len(parts) != 3:
        return None
    name, version, architecture = parts
    if (not _PACKAGE_NAME_RE.fullmatch(name)
            or not _ARCHITECTURE_RE.fullmatch(architecture)
            or not version
            or any(char.isspace() for char in version)):
        return None

    return {"name": name, "version": version, "architecture": architecture}


def _read_lfs_pointer(path):
    """Dosya Git LFS pointer'ıysa gerçek nesnenin boyut ve SHA256 bilgisini alır."""
    try:
        with open(path, "rb") as stream:
            header = stream.read(1024).decode("ascii")
    except (OSError, UnicodeDecodeError):
        return None

    lines = header.splitlines()
    if not lines or lines[0] != _LFS_VERSION:
        return None

    digest = None
    size = None
    for line in lines[1:]:
        oid_match = _LFS_OID_RE.fullmatch(line)
        if oid_match:
            digest = oid_match.group(1).lower()
            continue
        size_match = _LFS_SIZE_RE.fullmatch(line)
        if size_match:
            size = int(size_match.group(1))

    if digest is None or size is None:
        return None
    return {"sha256": digest, "size": size}


def _control_metadata(path):
    """.deb içindeki isteğe bağlı alanları alır; dosya adı temel kaynaktır."""
    rc, out, _err = utils.run_cmd(["dpkg-deb", "-f", path])
    if rc != 0:
        return {}
    return utils.parse_control(out)


def scan_deb(path):
    """
    Bir .deb dosyasından (paket sözlüğü, bağımlılık listesi) üretir.

    Paket adı, sürümü ve mimarisi daima dosya adından alınır; içerik okunamasa
    bile bu alanlarla veritabanı kaydı oluşturulur. Dosya adı beklenen biçimde
    değilse None döner.
    """
    filename_info = parse_deb_filename(path)
    if filename_info is None:
        return None

    lfs_info = _read_lfs_pointer(path)
    control = {} if lfs_info else _control_metadata(path)

    # Dosya adındaki kimlik bilgileri otoritatiftir. LFS pointer'ında görünen
    # boyut/SHA gerçek .deb nesnesine aittir; pointer'ın kendisine değil.
    name = filename_info["name"]
    version = filename_info["version"]
    architecture = filename_info["architecture"]
    if lfs_info:
        size = lfs_info["size"]
        sha256 = lfs_info["sha256"]
        md5sum = None  # LFS pointer'ı MD5 bilgisini içermez
    else:
        size = os.path.getsize(path)
        sha256 = security.sha256_file(path)
        md5sum = security.md5_file(path)

    _epoch, _upstream, revision = utils.split_version(version)
    try:
        release = int(revision) if revision else 1
    except ValueError:
        release = 1

    # Description: ilk satır özet, gerisi uzun açıklama. Kontrol bilgisi yoksa
    # paket adı özet olarak kullanılır; böylece dosya adından oluşan kayıtlar da
    # arama/listede anlamlı görünür.
    desc_lines = (control.get("Description") or "").splitlines()
    synopsis = desc_lines[0].strip() if desc_lines else name
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
                _dep_name, _op, dep_version = alternatives[0][0]
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
        "architecture": architecture,
        "description": synopsis,
        "long_description": long_desc,
        "maintainer": control.get("Maintainer"),
        "homepage": control.get("Homepage"),
        "license": control.get("License"),
        "section": control.get("Section"),
        "priority": control.get("Priority", "optional"),
        "filename": os.path.basename(path),
        "size": size,
        "installed_size": installed_size,
        "sha256": sha256,
        "md5sum": md5sum,
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
            print("✗ atlanıyor (dosya adı <paket>_<sürüm>_<mimari>.deb biçiminde değil): %s"
                  % os.path.basename(path))
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
    if summary["skipped"]:
        print("Atlanan .deb dosyaları: %s" % ", ".join(summary["skipped"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

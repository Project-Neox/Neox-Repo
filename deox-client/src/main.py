# -*- coding: utf-8 -*-
"""
DEOX ana giriş noktası — argparse tabanlı terminal arayüzü.

Temel işlemler:
  deox -S <paket>        paket kur (bağımlılıklarıyla)
  deox -R <paket>        paket kaldır (-Rs: bağımlılıklarla, -Rns: config ile)
  deox -U <dosya.deb>    yerel .deb dosyasından kur
  deox -Q                kurulu paketleri listele (-Qs/-Qi/-Ql/-Qo ile sorgu)

Arama ve bilgi:
  deox -Ss <anahtar>     depoda ara
  deox -Si <paket>       paket detayları

Güncelleme:
  deox -Sy               veritabanını senkronize et
  deox -Su               tüm paketleri güncelle
  deox -Syu              sync + update
  deox -Syyu             zorla sync + update

Önbellek:
  deox -Sc               eski önbelleği temizle
  deox -Scc              tüm önbelleği temizle

Ek komutlar:
  deox --history / --rollback / --stats / --doctor / --export / --import
  deox --clean-orphans / --check-updates / --add-repo / --remove-repo
  deox --list-repos / --vote / --snapshot / --version / --help

Tüm komutlar --json ile JSON çıktısı üretebilir (GUI uyumu).
"""

import argparse
import configparser
import json
import os
import shutil
import sys

from . import cache as cache_mod
from . import database as db_mod
from . import downloader as dl
from . import installer as inst_mod
from . import resolver as res_mod
from . import searcher as sea_mod
from . import security
from . import ui
from . import updater as upd_mod
from . import utils


# ---------------------------------------------------------------------------
# Argüman ayrıştırıcı
# ---------------------------------------------------------------------------

def build_parser():
    """deox komut satırı argüman ayrıştırıcısını kurar."""
    p = argparse.ArgumentParser(
        prog="deox",
        description="🔮 DEOX — Debian tabanlı sistemler için topluluk paket "
                    "yöneticisi (AUR benzeri; hazır .deb dağıtımı, kaynak "
                    "derleme yok)",
        epilog="Örnekler:\n"
               "  deox -Sy                 depo veritabanını senkronize et\n"
               "  deox -S htop             htop paketini kur\n"
               "  deox -Ss htop            depoda ara\n"
               "  deox -Si htop            paket detayları\n"
               "  deox -Su                 tüm paketleri güncelle\n"
               "  deox -Rns htop           htop'u configleriyle kaldır\n"
               "  deox -U ./paket.deb      yerel .deb'den kur\n"
               "  deox -Q                  kurulu paketleri listele\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("packages", nargs="*", metavar="paket",
                   help="paket adları / anahtar kelimeler")

    # pacman tarzı işlem bayrakları (birleştirilebilir: -Syu, -Rns, -Scc...)
    p.add_argument("-S", "--install", action="store_true",
                   help="paket kur (-Ss: ara, -Si: bilgi, -Sy: sync, -Su: güncelle,"
                        " -Sc/-Scc: önbellek temizle)")
    p.add_argument("-R", "--remove", action="store_true",
                   help="paket kaldır (-Rs: bağımlılıklarla, -Rns: config dahil)")
    p.add_argument("-Q", "--query", action="store_true",
                   help="kurulu paketleri sorgula (-Qs: ara, -Qi: bilgi,"
                        " -Ql: dosyalar, -Qo: dosya sahibi)")
    p.add_argument("-U", "--upload", nargs="+", metavar="DOSYA.deb",
                   help="yerel .deb dosyasından kur")
    p.add_argument("-y", "--refresh", action="count", default=0,
                   help="-Sy: veritabanı yenile, -Syy: zorla yenile")
    p.add_argument("-u", "--sysupgrade", action="store_true",
                   help="-Su ile sistemi güncelle")
    p.add_argument("-s", "--search", action="store_true",
                   help="-Ss: depoda ara, -Qs: kurulu ara, -Rs: bağımlılıklarıyla kaldır")
    p.add_argument("-i", "--info", action="store_true",
                   help="-Si: paket bilgisi, -Qi: kurulu paket bilgisi")
    p.add_argument("-l", "--list", action="store_true",
                   help="-Ql: paketin dosya listesi")
    p.add_argument("-o", "--owns", action="store_true",
                   help="-Qo: dosyanın sahibi paketi bul")
    p.add_argument("-c", "--clean", action="count", default=0,
                   help="-Sc: eski önbelleği temizle, -Scc: tüm önbelleği temizle")
    p.add_argument("-n", "--purge", action="store_true",
                   help="-Rns: yapılandırma dosyalarıyla birlikte kaldır")
    p.add_argument("-w", "--downloadonly", action="store_true",
                   help="sadece indir, kurma")

    # uzun komutlar
    p.add_argument("--yes", action="store_true",
                   help="onay sormadan devam et")
    p.add_argument("--history", action="store_true",
                   help="işlem geçmişi")
    p.add_argument("--rollback", metavar="ID",
                   help="geçmişteki işlemi geri al")
    p.add_argument("--stats", action="store_true",
                   help="istatistikler")
    p.add_argument("--doctor", action="store_true",
                   help="sistem bütünlüğü kontrolü")
    p.add_argument("--export", nargs="?", const="-", default=None, metavar="DOSYA",
                   help="kurulu paketleri dışa aktar (varsayılan: stdout)")
    p.add_argument("--import", dest="import_file", metavar="DOSYA",
                   help="paket listesini içe aktar ve kur")
    p.add_argument("--clean-orphans", action="store_true",
                   help="yetim (gereksiz) paketleri kaldır")
    p.add_argument("--check-updates", action="store_true",
                   help="güncelleme kontrolü")
    p.add_argument("--add-repo", nargs=2, metavar=("İSİM", "URL"),
                   help="depo ekle")
    p.add_argument("--remove-repo", metavar="İSİM",
                   help="depo kaldır")
    p.add_argument("--list-repos", action="store_true",
                   help="depo listesi")
    p.add_argument("--vote", metavar="PAKET",
                   help="pakete oy ver (+1)")
    p.add_argument("--snapshot", nargs="+", metavar="KOMUT",
                   help="snapshot: create AD | restore AD | list")
    p.add_argument("--version", action="store_true",
                   help="sürüm bilgisi")

    # genel seçenekler
    p.add_argument("--json", action="store_true",
                   help="makine tarafından okunabilir JSON çıktı")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="ayrıntılı çıktı")
    p.add_argument("-d", "--debug", action="store_true",
                   help="hata ayıklama çıktısı")
    p.add_argument("--no-confirm", action="store_true",
                   help="onay sorma")
    p.add_argument("--no-color", action="store_true",
                   help="renkleri kapat")
    p.add_argument("--arch", metavar="MİMARİ",
                   help="hedef mimari (örn. amd64, arm64; varsayılan: otomatik)")
    return p


# ---------------------------------------------------------------------------
# Bağlam (ortak servisler)
# ---------------------------------------------------------------------------

class Context:
    """Komutların ortak eriştiği servisler (config, db'ler, motorlar)."""

    def __init__(self, args):
        self.args = args
        self.paths = utils.system_paths()
        self.config = utils.Config(self.paths)
        utils.setup_logging(self.config.log_file, args.verbose, args.debug)
        ui.init(color=self.config.color and not args.no_color,
                json_mode=args.json)
        self.arch = args.arch or self.config.architecture
        self.sync_db = db_mod.Database(self.paths["sync_db"])
        self.local_db = db_mod.Database(self.paths["local_db"])
        self.cache = cache_mod.CacheManager(self.config.cache_dir).ensure()
        self.downloader = dl.Downloader(self.config)
        self.installer = inst_mod.Installer(
            self.config, self.paths, self.local_db, self.sync_db,
            self.cache, self.downloader)
        self.searcher = sea_mod.Searcher(self.sync_db, self.local_db, self.arch)
        self.resolver = res_mod.Resolver(self.sync_db, self.local_db, self.arch)
        self.updater = upd_mod.Updater(
            self.config, self.paths, self.sync_db, self.local_db,
            self.cache, self.downloader)

    @property
    def no_confirm(self):
        """Onay sorulmayacak mı? (bayrak veya yapılandırma)"""
        return (self.args.no_confirm or self.args.yes
                or self.config.no_confirm)


# ---------------------------------------------------------------------------
# Yardımcı: paket indirme URL'si ve önbellek
# ---------------------------------------------------------------------------

def _repo_url(ctx, pkg):
    """Paketin bulunduğu deponun temel URL'sini döndürür."""
    repo = ctx.local_db.get_repo(pkg.get("repo") or "deox")
    if not repo:
        raise utils.DeoxError(
            "'%s' deposu tanımlı değil." % pkg.get("repo", "deox"))
    return repo["url"].rstrip("/")


def _download_items_for(ctx, packages):
    """
    Plandaki paketler için DownloadItem listesi üretir.
    Önbellekte geçerli (checksum'ı tutan) dosyası olanlar indirilmez.
    Dönüş: (indirilecekler, önbellektekiler {name: path})
    """
    to_download = []
    cached = {}
    for pkg in packages:
        url = "%s/deoxpool/%s" % (_repo_url(ctx, pkg), pkg["filename"])
        item = dl.DownloadItem(pkg["name"], url, ctx.cache.pkg_dir,
                               pkg["filename"], pkg.get("sha256"),
                               pkg.get("size"), pkg.get("md5sum"))
        cache_path = ctx.cache.path_for(pkg["filename"])
        if os.path.isfile(cache_path):
            ok, _msg = security.verify_checksums(
                cache_path, pkg.get("sha256"), pkg.get("md5sum"))
            if ok:
                cached[pkg["name"]] = cache_path
                continue
        to_download.append(item)
    return to_download, cached


# ---------------------------------------------------------------------------
# Komutlar
# ---------------------------------------------------------------------------

def cmd_install(ctx, names, action="install"):
    """Paket(ler)i bağımlılıklarıyla kurar (deox -S / -Su akışı)."""
    plan = ctx.installer and ctx.resolver_resolve(names, action)
    if plan.missing:
        for m in plan.missing:
            ui.error("depoda bulunamadı: %s" % m)
    if plan.conflicts:
        for c in plan.conflicts:
            ui.error("çakışma: %s" % c)
    for w in plan.warnings:
        ui.warning(w)
    if plan.missing or plan.conflicts:
        raise utils.DeoxError("çözümleme başarısız; kurulum iptal edildi.")
    if not plan.to_install:
        ui.info("Kurulacak yeni paket yok; hepsi zaten kurulu.")
        return plan.to_dict()

    # onay kutusu
    if not ctx.no_confirm:
        rows = [{"name": p["name"],
                 "version": "%s-%s" % (p["version"], p.get("release", 1)),
                 "size": p.get("size") or 0} for p in plan.to_install]
        ok = ui.confirm_box("Kurulacak Paketler (%d)" % len(rows), rows,
                            plan.total_download, plan.total_installed_size)
        if not ok:
            ui.warning("Kurulum iptal edildi.")
            return plan.to_dict()

    # indirme (önbellek + paralel)
    to_download, cached = _download_items_for(ctx, plan.to_install)
    paths = dict(cached)
    if to_download:
        ui.info("%d paket indiriliyor..." % len(to_download))
        paths.update(ctx.downloader.download_many(to_download))

    if ctx.args.downloadonly:
        ui.success("Paketler indirildi, kurulum yapılmadı (-w).")
        return {**plan.to_dict(), "downloaded": sorted(paths.values())}

    ordered = [paths[p["name"]] for p in plan.to_install]
    reasons = {p["name"]: plan.reasons.get(p["name"], "explicit")
               for p in plan.to_install}
    installed = ctx.installer.install_files(ordered, reasons=reasons,
                                            action=action)
    for rec in installed:
        ui._emit("✅ %s %s başarıyla kuruldu!"
                 % (ui.pkg(rec["name"]), ui.ver(rec["version"])))
    return {**plan.to_dict(), "installed": installed}


def cmd_remove(ctx, names, recursive=False, purge=False):
    """Paket(ler)i kaldırır (deox -R / -Rs / -Rns)."""
    removed = ctx.installer.remove(names, purge=purge, recursive=recursive)
    return {"removed": removed, "purge": purge, "recursive": recursive}


def cmd_upload(ctx, files):
    """Yerel .deb dosyalarını kurar (deox -U)."""
    paths = []
    for f in files:
        if not os.path.isfile(f):
            raise utils.DeoxError("dosya bulunamadı: %s" % f)
        paths.append(os.path.abspath(f))
    installed = ctx.installer.install_files(paths, action="install")
    for rec in installed:
        ui._emit("✅ %s %s başarıyla kuruldu!"
                 % (ui.pkg(rec["name"]), ui.ver(rec["version"])))
    return {"installed": installed}


def cmd_query(ctx, args):
    """Kurulu paket sorguları (deox -Q / -Qs / -Qi / -Ql / -Qo)."""
    if args.owns:  # -Qo <dosya>
        results = []
        for f in args.packages:
            owner = ctx.installer.owner_of(f)
            results.append({"file": f, "owner": owner})
            if owner:
                ui.success("%s → %s" % (f, ui.pkg(owner)))
            else:
                ui.warning("%s hiçbir pakete ait değil." % f)
        return results

    if args.list:  # -Ql <paket>
        results = []
        for name in args.packages:
            files = ctx.installer.files_of(name)
            ui.header("%s dosya listesi:" % name)
            for f in files:
                ui._emit("  %s" % f)
            results.append({"package": name, "files": files})
        return results

    if args.search:  # -Qs <anahtar>
        keyword = args.packages[0] if args.packages else ""
        results = ctx.searcher.search_installed(keyword)
        ui.header("Kurulu paketlerde '%s' araması (%d sonuç):"
                  % (keyword, len(results)))
        for r in results:
            line = "  %s %s" % (ui.pkg(r["name"]), ui.ver(r["version"]))
            if r.get("install_reason") == "dependency":
                line += " " + ui.dim("(bağımlılık)")
            ui._emit(line)
            if r.get("description"):
                ui._emit("    %s" % r["description"])
        return {"keyword": keyword, "results": results}

    if args.info:  # -Qi <paket>
        results = []
        for name in (args.packages or [None]):
            if name is None:
                continue
            info = ctx.searcher.info(name)
            results.append(info)
            render_info(info)
        return results

    # -Q: tüm kurulu paketler
    installed = ctx.local_db.get_installed()
    ui.header("Kurulu paketler (%d):" % len(installed))
    for i in installed:
        line = "  %-28s %s" % (ui.pkg(i["name"]), ui.ver(i["version"]))
        if i.get("install_reason") == "dependency":
            line += "  " + ui.dim("(bağımlılık)")
        ui._emit(line)
    return {"count": len(installed), "packages": installed}


def cmd_search_remote(ctx, keyword):
    """Depoda paket arar (deox -Ss)."""
    results = ctx.searcher.search_remote(keyword)
    if not results:
        ui.warning("'%s' ile eşleşen paket bulunamadı." % keyword)
        return {"keyword": keyword, "count": 0, "results": []}
    ui.header("'%s' araması (%d sonuç):" % (keyword, len(results)))
    for r in results:
        tag = " " + ui.green("[kurulu]") if r.get("installed") else ""
        section = ui.dim("[%s]" % (r.get("section") or "bilinmiyor"))
        ui._emit("%s %s %s%s"
                 % (ui.bold("%s/%s" % (r.get("repo", "deox"), r["name"])),
                    ui.ver("%s-%s" % (r["version"], r.get("release", 1))),
                    section, tag))
        if r.get("description"):
            ui._emit("    %s" % r["description"])
    return {"keyword": keyword, "count": len(results), "results": results}


def cmd_info(ctx, name):
    """Paket detaylarını gösterir (deox -Si)."""
    info = ctx.searcher.info(name)
    render_info(info)
    return info


def render_info(info):
    """Paket detaylarını terminale yazar."""
    if info is None:
        raise utils.DeoxError("paket bulunamadı")
    if not info.get("found") and info.get("providers"):
        ui.warning("'%s' depoda yok; sağlayan paketler: %s"
                   % (info["name"],
                      ", ".join(p["name"] for p in info["providers"])))
        return
    if not info.get("in_repo", True):
        ui.header("Kurulu paket (depoda yok): %s" % ui.pkg(info["name"]))
        ui._emit("  Sürüm : %s" % ui.ver(info.get("version", "-")))
        ui._emit("  Tarih : %s" % (info.get("install_date") or "-"))
        return
    ui._emit("Depo            : %s" % (info.get("repo") or "-"))
    ui._emit("Paket           : %s" % ui.pkg(info["name"]))
    ui._emit("Sürüm           : %s" % ui.ver(info.get("version", "-")))
    if info.get("release"):
        ui._emit("Release         : %s" % info["release"])
    ui._emit("Mimari          : %s" % (info.get("architecture") or "-"))
    if info.get("description"):
        ui._emit("Açıklama        : %s" % info["description"])
    if info.get("long_description"):
        ui._emit("Uzun açıklama   :\n%s" % info["long_description"])
    if info.get("maintainer"):
        ui._emit("Bakımcı         : %s" % info["maintainer"])
    if info.get("homepage"):
        ui._emit("Web sitesi      : %s" % info["homepage"])
    if info.get("license"):
        ui._emit("Lisans          : %s" % info["license"])
    if info.get("section"):
        ui._emit("Bölüm           : %s" % info["section"])
    if info.get("size") is not None:
        ui._emit("İndirme boyutu  : %s" % ui.size_s(info["size"]))
    if info.get("installed_size"):
        ui._emit("Kurulu boyutu   : %s" % ui.size_s(info["installed_size"]))
    ui._emit("SHA256          : %s" % ui.dim(info.get("sha256") or "-"))
    ui._emit("İndirme sayısı  : %s" % info.get("download_count", 0))
    ui._emit("Oy              : %s" % info.get("votes", 0))
    if info.get("installed"):
        ui._emit("Durum           : %s"
                 % ui.green("[kurulu] %s" % info.get("installed_version")))
    deps = info.get("dependencies") or {}
    for dep_type in ("depends", "recommends", "suggests", "conflicts",
                     "replaces", "provides"):
        rows = deps.get(dep_type) or []
        if rows:
            ui._emit("%-15s: %s"
                     % (dep_type.capitalize(),
                        ", ".join(r["dep_name"] for r in rows)))


def cmd_sync(ctx, force=False):
    """Depo veritabanlarını senkronize eder (deox -Sy / -Syy)."""
    ui.print_banner()
    return ctx.updater.sync(force=force)


def cmd_upgrade(ctx, names=None):
    """Tüm paketleri (veya verilenleri) günceller (deox -Su)."""
    if names is None:
        upgrades = ctx.updater.check_updates()
        names = [u["name"] for u in upgrades]
        if not names:
            ui.success("Tüm paketler güncel. ✓")
            return {"updates": [], "installed": []}
        ui.info("%d paket güncellenecek: %s"
                % (len(names), ", ".join(names)))
    return cmd_install(ctx, names, action="update")


def cmd_cache_clean(ctx, count):
    """Önbelleği temizler (deox -Sc / -Scc)."""
    all_files = count >= 2
    mode = "tümü" if all_files else "eski dosyalar"
    ui.info("Önbellek temizleniyor (%s)..." % mode)
    result = ctx.cache.clean(all_files=all_files)
    ui.success("%d dosya silindi, %s boşaltıldı."
               % (result["removed"], ui.size_s(result["freed_bytes"])))
    return {"mode": mode, **result}


def cmd_history(ctx, limit=50):
    """İşlem geçmişini gösterir (deox --history)."""
    rows = ctx.local_db.get_history(limit)
    if not rows:
        ui.info("Geçmiş kaydı yok.")
        return {"history": []}
    ui.table(["ID", "Tarih", "İşlem", "Paket", "Eski", "Yeni", "Durum"],
             [[r["id"], r["timestamp"], r["action"], r["package_name"],
               r.get("from_version") or "-", r.get("to_version") or "-",
               "✓" if r["success"] else "✗"] for r in rows])
    return {"history": rows}


def cmd_rollback(ctx, history_id):
    """Geçmişteki bir işlemi geri alır (deox --rollback ID)."""
    try:
        hid = int(history_id)
    except ValueError:
        raise utils.DeoxError("geçersiz ID: %s" % history_id)
    result = ctx.installer.rollback(hid)
    if result.get("packages"):
        ui.success("✅ #%d işlemi geri alındı: %s"
                   % (hid, ", ".join(result["packages"])))
    return result


def cmd_stats(ctx):
    """İstatistikleri gösterir (deox --stats)."""
    data = {
        "sync": ctx.sync_db.stats(),
        "local": {
            "installed": ctx.local_db.installed_count(),
            "history_entries": ctx.local_db.history_count(),
        },
        "cache": {"files": len(ctx.cache.list()),
                  "size_bytes": ctx.cache.size()},
        "top_downloads": ctx.sync_db.top_downloads(10),
        "recent": ctx.sync_db.recent(10),
    }
    if not ui.JSON_MODE:
        s = data["sync"]
        ui._emit(ui.header("DEOX İstatistikleri"))
        ui._emit("  Depodaki paket sayısı : %d" % s["packages"])
        ui._emit("  Toplam bağımlılık     : %d" % s["dependencies"])
        ui._emit("  Toplam indirme        : %d" % s["total_downloads"])
        ui._emit("  Toplam oy             : %d" % s["total_votes"])
        ui._emit("  İşaretli paket        : %d" % s["flagged"])
        ui._emit("  Kurulu paket          : %d" % data["local"]["installed"])
        ui._emit("  Geçmiş kaydı          : %d" % data["local"]["history_entries"])
        ui._emit("  Önbellek              : %d dosya, %s"
                 % (data["cache"]["files"], ui.size_s(data["cache"]["size_bytes"])))
        ui._emit(ui.header("En çok indirilenler"))
        for p in data["top_downloads"]:
            ui._emit("  %s %s — %d indirme"
                     % (ui.pkg(p["name"]), ui.ver(p["version"]),
                        p["download_count"]))
        ui._emit(ui.header("Son eklenenler"))
        for p in data["recent"]:
            ui._emit("  %s %s (%s)"
                     % (ui.pkg(p["name"]), ui.ver(p["version"]),
                        p.get("upload_date") or "-"))
    return data


def cmd_doctor(ctx):
    """Sistem bütünlüğü kontrolü (deox --doctor)."""
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        mark = ui.green("✓") if ok else ui.red("✗")
        line = "  %s %s" % (mark, name)
        if detail:
            line += ui.dim(" — %s" % detail)
        ui._emit(line)

    ui._emit(ui.header("DEOX sistem kontrolü (--doctor)"))
    check("root yetkisi", utils.is_root() or bool(utils.ROOT_PREFIX),
          "test modu (DEOX_ROOT)" if utils.ROOT_PREFIX else "")
    check("dpkg mevcut", shutil.which("dpkg") is not None)
    check("dpkg-deb mevcut", shutil.which("dpkg-deb") is not None)
    check("yapılandırma dizini", os.path.isdir(ctx.paths["etc"]),
          ctx.paths["etc"])
    sync_ok = (os.path.isfile(ctx.paths["sync_db"])
               and ctx.sync_db.integrity())
    check("sync veritabanı", sync_ok,
          "%d paket" % ctx.sync_db.count_packages() if sync_ok else "yok/bozuk")
    check("yerel veritabanı", ctx.local_db.integrity())
    check("önbellek dizini", os.path.isdir(ctx.cache.pkg_dir),
          "%s (%d dosya)" % (ctx.cache.root, len(ctx.cache.list())))
    check("log dosyası yazılabilir",
          _log_writable(ctx.config.log_file), ctx.config.log_file)

    # dpkg bütünlüğü (sistemdeki paketler için)
    rc, out, _ = utils.run_cmd(["dpkg", "--audit"])
    check("dpkg --audit temiz", rc == 0 and not out.strip(),
          out.strip()[:80] if out.strip() else "")

    # bozuk paket var mı?
    rc, out, _ = utils.run_cmd(
        ["dpkg-query", "-W", "-f=${db:Status-Abbrev} ${Package}\\n"])
    broken = [l for l in out.splitlines()
              if l and not l.startswith("ii ")]
    check("bozuk paket yok", rc == 0 and not broken,
          "%d şüpheli" % len(broken) if broken else "")

    # internet bağlantısı
    check("internet bağlantısı", _net_ok())

    ok_count = sum(1 for c in checks if c["ok"])
    ui._emit("\n%d/%d kontrol başarılı." % (ok_count, len(checks)))
    return {"checks": checks, "passed": ok_count, "total": len(checks)}


def _log_writable(path):
    """Log dosyasının yazılabilir olup olmadığını denetler."""
    try:
        utils.ensure_dir(os.path.dirname(path))
        with open(path, "a", encoding="utf-8"):
            pass
        return True
    except OSError:
        return False


def _net_ok():
    """İnternet bağlantısı var mı? (github.com'a kısa bir istek)"""
    try:
        import urllib.request
        urllib.request.urlopen("https://github.com", timeout=5)
        return True
    except Exception:  # noqa: BLE001 - ağ durumu önemli değil
        return False


def cmd_export(ctx, dest):
    """Kurulu paketleri dışa aktarır (deox --export [DOSYA])."""
    installed = ctx.local_db.get_installed()
    lines = ["%s=%s" % (i["name"], i["version"]) for i in installed]
    text = "\n".join(lines) + "\n"
    if dest in (None, "-"):
        if not ui.JSON_MODE:
            sys.stdout.write(text)
    else:
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)
        ui.success("%d paket %s dosyasına aktarıldı." % (len(lines), dest))
    return {"count": len(lines), "packages": lines, "destination": dest or "-"}


def cmd_import(ctx, path):
    """Paket listesini içe aktarır ve kurar (deox --import DOSYA)."""
    if not os.path.isfile(path):
        raise utils.DeoxError("dosya bulunamadı: %s" % path)
    names = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            names.append(line.split("=")[0].split()[0])
    ui.info("%d paket içe aktarılıyor..." % len(names))
    return cmd_install(ctx, names)


def cmd_clean_orphans(ctx):
    """Yetim paketleri kaldırır (deox --clean-orphans)."""
    orphans = ctx.resolver.find_orphans()
    if not orphans:
        ui.success("Yetim paket bulunamadı.")
        return {"orphans": [], "removed": []}
    ui.info("%d yetim paket bulundu:" % len(orphans))
    for o in orphans:
        ui._emit("  %s %s" % (ui.pkg(o["name"]), ui.ver(o["version"])))
    if not ctx.no_confirm:
        if not ui.confirm("Yetim paketler kaldırılsın mı? [E/h]"):
            ui.warning("İptal edildi.")
            return {"orphans": [o["name"] for o in orphans], "removed": []}
    removed = ctx.installer.remove([o["name"] for o in orphans])
    return {"orphans": [o["name"] for o in orphans], "removed": removed}


def cmd_check_updates(ctx):
    """Güncelleme kontrolü (deox --check-updates)."""
    upgrades = ctx.updater.check_updates()
    if not upgrades:
        ui.success("Tüm paketler güncel. ✓")
        return {"updates": []}
    ui.header("%d güncelleme var:" % len(upgrades))
    for u in upgrades:
        ui._emit("  %s %s → %s"
                 % (ui.pkg(u["name"]), ui.ver(u["installed_version"]),
                    ui.ver(u["available_version"])))
    return {"updates": upgrades}


def cmd_add_repo(ctx, name, url):
    """Depo ekler (deox --add-repo İSİM URL)."""
    if not url.startswith(("http://", "https://")):
        raise utils.DeoxError("depo URL'si http:// veya https:// ile başlamalı.")
    ctx.local_db.upsert_repo(name, url, True, 100)
    ctx.sync_db.upsert_repo(name, url, True, 100)
    _write_repo_conf(ctx.paths["etc"], name, url, True, 100)
    ui.success("'%s' deposu eklendi: %s" % (name, url))
    return {"name": name, "url": url, "enabled": True, "priority": 100}


def cmd_remove_repo(ctx, name):
    """Depo kaldırır (deox --remove-repo İSİM)."""
    if not ctx.local_db.get_repo(name):
        raise utils.DeoxError("'%s' deposu tanımlı değil." % name)
    ctx.local_db.remove_repo(name)
    ctx.sync_db.remove_repo(name)
    _remove_repo_conf(ctx.paths["etc"], name)
    ui.success("'%s' deposu kaldırıldı." % name)
    return {"removed": name}


def cmd_list_repos(ctx):
    """Depo listesini gösterir (deox --list-repos)."""
    repos = ctx.local_db.list_repos()
    if not repos:
        # henüz senkronize edilmemişse yapılandırma dosyalarından göster
        repos = utils.load_repos(ctx.config)
        for r in repos:
            r["last_sync"] = None
    if not repos:
        ui.warning("Tanımlı depo yok. 'deox --add-repo <isim> <url>' ile ekleyin.")
        return {"repositories": []}
    ui.table(["Depo", "URL", "Etkin", "Öncelik", "Son Sync"],
             [[r["name"], r["url"], "✓" if r["enabled"] else "✗",
               r["priority"], r.get("last_sync") or "-"] for r in repos])
    return {"repositories": repos}


def _write_repo_conf(etc_dir, name, url, enabled, priority):
    """repos.conf dosyasına depo bölümü ekler/günceller."""
    utils.ensure_dir(etc_dir)
    conf = os.path.join(etc_dir, "repos.conf")
    cp = configparser.ConfigParser()
    if os.path.isfile(conf):
        cp.read(conf, encoding="utf-8")
    if not cp.has_section(name):
        cp.add_section(name)
    cp.set(name, "Server", url)
    cp.set(name, "Enabled", "true" if enabled else "false")
    cp.set(name, "Priority", str(priority))
    with open(conf, "w", encoding="utf-8") as f:
        f.write("# DEOX depo kaynakları\n")
        cp.write(f)


def _remove_repo_conf(etc_dir, name):
    """repos.conf dosyasından depo bölümünü kaldırır."""
    conf = os.path.join(etc_dir, "repos.conf")
    if not os.path.isfile(conf):
        return
    cp = configparser.ConfigParser()
    cp.read(conf, encoding="utf-8")
    if cp.has_section(name):
        cp.remove_section(name)
        with open(conf, "w", encoding="utf-8") as f:
            f.write("# DEOX depo kaynakları\n")
            cp.write(f)


def cmd_vote(ctx, name):
    """Pakete oy verir (deox --vote PAKET)."""
    pkg = ctx.sync_db.get_package(name)
    if not pkg:
        raise utils.DeoxError("depoda bulunamadı: %s" % name)
    # oylar yerel kuyruğa yazılır (çevrimdışı); oy sunucusu tanımlanınca
    # senkronize edilecek şekilde tasarlandı
    votes = utils.read_json(ctx.paths["votes"], [])
    votes.append({"package": name, "vote": 1, "time": utils.now_str()})
    utils.write_json(ctx.paths["votes"], votes)
    ctx.sync_db.vote(name, 1)
    ui.success("%s paketine oy verdiniz. (çevrimdışı kuyruğa eklendi)"
               % ui.pkg(name))
    return {"package": name, "votes": (pkg.get("votes") or 0) + 1,
            "queued": len(votes)}


def cmd_snapshot(ctx, argv):
    """Snapshot işlemleri (deox --snapshot create/restore/list)."""
    if not argv:
        raise utils.DeoxError(
            "kullanım: deox --snapshot create AD | restore AD | list")
    command = argv[0].lower()
    snap_dir = ctx.paths["snapshots"]
    utils.ensure_dir(snap_dir)

    if command == "create":
        name = argv[1] if len(argv) > 1 else "snapshot-%s" % utils.now_str()
        installed = ctx.local_db.get_installed()
        data = {
            "name": name,
            "created": utils.now_str(),
            "packages": {i["name"]: i["version"] for i in installed},
        }
        utils.write_json(os.path.join(snap_dir, name + ".json"), data)
        ui.success("'%s' snapshot'ı oluşturuldu (%d paket)."
                   % (name, len(installed)))
        return data

    if command == "list":
        snapshots = []
        for f in sorted(os.listdir(snap_dir)):
            if f.endswith(".json"):
                snapshots.append(utils.read_json(os.path.join(snap_dir, f), {}))
        if not snapshots:
            ui.info("Snapshot yok.")
        else:
            ui.table(["İsim", "Tarih", "Paket Sayısı"],
                     [[s.get("name"), s.get("created"),
                       len(s.get("packages", {}))] for s in snapshots])
        return {"snapshots": snapshots}

    if command == "restore":
        if len(argv) < 2:
            raise utils.DeoxError("kullanım: deox --snapshot restore AD")
        name = argv[1]
        path = os.path.join(snap_dir, name + ".json")
        if not os.path.isfile(path):
            raise utils.DeoxError("snapshot bulunamadı: %s" % name)
        data = utils.read_json(path, {})
        names = list(data.get("packages", {}).keys())
        ui.info("'%s' snapshot'ı geri yükleniyor (%d paket)..."
                % (name, len(names)))
        return cmd_install(ctx, names)

    raise utils.DeoxError(
        "bilinmeyen snapshot komutu: %s (create | restore | list)" % command)


# ---------------------------------------------------------------------------
# Komut yönlendirme
# ---------------------------------------------------------------------------

def dispatch(ctx):
    """Ayrıştırılan argümanlara göre ilgili komutu çalıştırır."""
    args = ctx.args

    if args.install:
        if args.search:  # -Ss <anahtar>
            keyword = args.packages[0] if args.packages else ""
            return cmd_search_remote(ctx, keyword)
        if args.info:  # -Si <paket>
            if not args.packages:
                raise utils.DeoxError("paket adı gerekli. Örn: deox -Si htop")
            return [cmd_info(ctx, n) for n in args.packages]
        if args.clean:  # -Sc / -Scc
            return cmd_cache_clean(ctx, args.clean)
        # -Sy / -Su / -Syu / -Syyu / -S <paket...>
        data = {}
        if args.refresh:
            data["sync"] = cmd_sync(ctx, force=args.refresh >= 2)
        if args.sysupgrade:
            data["upgrade"] = cmd_upgrade(ctx)
        if args.packages:
            data["install"] = cmd_install(ctx, args.packages)
        if not (args.refresh or args.sysupgrade or args.packages):
            raise utils.DeoxError(
                "işlem belirtilmedi. Örn: deox -S htop, deox -Sy, deox -Su")
        return data

    if args.remove:
        if not args.packages:
            raise utils.DeoxError(
                "kaldırılacak paket adı gerekli. Örn: deox -R htop")
        return cmd_remove(ctx, args.packages,
                          recursive=args.search, purge=args.purge)

    if args.query:
        return cmd_query(ctx, args)

    if args.upload:
        return cmd_upload(ctx, args.upload)

    if args.history:
        return cmd_history(ctx)
    if args.rollback:
        return cmd_rollback(ctx, args.rollback)
    if args.stats:
        return cmd_stats(ctx)
    if args.doctor:
        return cmd_doctor(ctx)
    if args.export is not None:
        return cmd_export(ctx, args.export)
    if args.import_file:
        return cmd_import(ctx, args.import_file)
    if args.clean_orphans:
        return cmd_clean_orphans(ctx)
    if args.check_updates:
        return cmd_check_updates(ctx)
    if args.add_repo:
        return cmd_add_repo(ctx, *args.add_repo)
    if args.remove_repo:
        return cmd_remove_repo(ctx, args.remove_repo)
    if args.list_repos:
        return cmd_list_repos(ctx)
    if args.vote:
        return cmd_vote(ctx, args.vote)
    if args.snapshot:
        return cmd_snapshot(ctx, args.snapshot)

    ui.print_banner()
    print("Yardım için: deox --help")
    return None


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------

def main(argv=None):
    """DEOX komut satırı giriş noktası."""
    args = build_parser().parse_args(argv)

    if args.version:
        data = {"name": "DEOX", "version": utils.APP_VERSION,
                "python": sys.version.split()[0]}
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            ui.init(color=not args.no_color)
            ui.print_banner()
            print("DEOX v%s — Python %s"
                  % (utils.APP_VERSION, sys.version.split()[0]))
        return 0

    try:
        ctx = Context(args)
        # resolver'ı upgrade kipiyle bağla (cmd_install upgrade=True kullanır)
        ctx.resolver = __import__("src.resolver", fromlist=["Resolver"]).Resolver(
            ctx.sync_db, ctx.local_db, ctx.arch) if False else None
        from .resolver import Resolver
        ctx.resolver = Resolver(ctx.sync_db, ctx.local_db, ctx.arch)

        def _resolve(names, action="install"):
            return ctx.resolver.resolve(names, upgrade=(action == "update"))

        ctx.resolver_resolve = _resolve

        data = dispatch(ctx)
        if args.json and data is not None:
            print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return 0
    except utils.DeoxError as exc:
        ui.error(str(exc))
        utils.LOGGER.error("hata: %s", exc)
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
    except KeyboardInterrupt:
        print()
        ui.warning("iptal edildi.")
        return 130


if __name__ == "__main__":
    sys.exit(main())

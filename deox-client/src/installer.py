# -*- coding: utf-8 -*-
"""
DEOX kurulum/kaldırma motoru — dpkg entegrasyonu.

- İndirilen .deb dosyaları `dpkg -i` ile kurulur
- Kaldırma `dpkg --remove` / `dpkg --purge` ile yapılır
- Her işlem yerel veritabanına ve geçmişe kaydedilir
- /etc/deox/hooks.d altındaki pre/post hook scriptleri çalıştırılır

Root değilken test modu (DEOX_ROOT tanımlıysa) `dpkg --root <rootfs>
--force-not-root` ile hedef rootfs'e kurulum yapar; bu sayede sisteme
dokunmadan uçtan uca test yapılabilir.
"""

import os
import subprocess

from . import security
from . import ui
from . import utils
from .downloader import DownloadItem
from .resolver import Resolver

# Test modunda dpkg'nin beklediği yardımcı programlar için PATH dizinleri
_SBIN_PATH = "/usr/local/sbin:/usr/sbin:/sbin:/usr/local/bin:/usr/bin:/bin"


class InstallError(utils.DeoxError):
    """Kurulum/kaldırma işlemi başarısız oldu."""


class Installer:
    """dpkg üzerinden paket kurma/kaldırma işlemleri."""

    def __init__(self, config, paths, local_db, sync_db, cache, downloader=None):
        self.config = config
        self.paths = paths
        self.local_db = local_db
        self.sync_db = sync_db
        self.cache = cache
        self.downloader = downloader
        # root değilsek ve DEOX_ROOT tanımlıysa test modunda rootfs'e kurarız
        self.test_mode = (not utils.is_root()) and bool(utils.ROOT_PREFIX)

    # ------------------------------------------------------------------
    # dpkg yardımcıları
    # ------------------------------------------------------------------

    def require_root(self):
        """Kurulum/kaldırma için root yetkisi ister (test modu hariç)."""
        if not utils.is_root() and not self.test_mode:
            raise InstallError(
                "bu işlem root yetkisi gerektirir. "
                "Lütfen 'sudo deox ...' ile çalıştırın.")

    def _dpkg_cmd(self):
        """Test modunda dpkg --root ile hedef rootfs'e kurulum komutu üretir."""
        cmd = ["dpkg"]
        if self.test_mode:
            rootfs = self.paths["rootfs"]
            utils.ensure_dir(os.path.join(rootfs, "var/lib/dpkg/updates"))
            # dpkg'nin ihtiyaç duyduğu boş durum dosyası
            status = os.path.join(rootfs, "var/lib/dpkg/status")
            if not os.path.exists(status):
                open(status, "a").close()
            cmd += ["--root", rootfs, "--force-not-root"]
        return cmd

    def _run_dpkg(self, args, timeout=600):
        """dpkg komutunu çalıştırır."""
        cmd = self._dpkg_cmd() + args
        utils.LOGGER.info("çalıştırılıyor: %s", " ".join(cmd))
        env = dict(os.environ)
        if self.test_mode:
            # dpkg --root, start-stop-daemon gibi programları PATH'te arar
            env["PATH"] = _SBIN_PATH
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=timeout, env=env)
        except FileNotFoundError:
            raise InstallError(
                "dpkg bulunamadı. Debian tabanlı bir sistemde misiniz?")
        except subprocess.TimeoutExpired:
            raise InstallError("dpkg zaman aşımına uğradı.")

    @staticmethod
    def _friendly_error(proc):
        """dpkg hata çıktısını kullanıcı dostu bir mesaja çevirir."""
        out = (proc.stdout or "") + (proc.stderr or "")
        if "dependency problems" in out or "depends on" in out:
            return ("Bağımlılık sorunu: bazı paketlerin bağımlılıkları "
                    "karşılanamadı.\n  'sudo apt -f install' ile sistem "
                    "bağımlılıklarını tamamlayın veya eksik paketleri "
                    "deox ile kurun.")
        if "is not installed" in out:
            return "Paket kurulu değil."
        if "trying to overwrite" in out:
            return ("Dosya çakışması: paket başka bir paketin dosyasının "
                    "üzerine yazıyor.")
        if "dpkg was interrupted" in out:
            return ("dpkg önceki bir işlemle meşgul görünüyor. "
                    "'sudo dpkg --configure -a' çalıştırın.")
        lines = [l for l in out.splitlines() if l.strip()]
        return "dpkg hatası: %s" % (lines[-1] if lines
                                    else "kod %d" % proc.returncode)

    @staticmethod
    def _deb_meta(path):
        """dpkg-deb -f ile .deb içinden temel metadata'yı okur."""
        rc, out, _ = utils.run_cmd(["dpkg-deb", "-f", path, "Package", "Version"])
        meta = {}
        if rc == 0:
            for line in out.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip()
        return meta

    def _local_pkg_id(self, name):
        """
        Paketin yerel veritabanındaki id'si.

        Yerel veritabanı (installed.package_id FK'sı ve GUI okuması için)
        paketin sync veritabanındaki kaydını da tutar; yoksa eklenir.
        """
        sync_pkg = self.sync_db.get_package(name)
        local_pkg = self.local_db.get_package(name)
        # yoksa, sürüm eskiyse veya üstveri tamamlanmamışsa sync kaydını aktar
        if sync_pkg and (not local_pkg
                          or local_pkg["version"] != sync_pkg["version"]
                          or not local_pkg.get("upload_date")):
            self.local_db.upsert_package(sync_pkg)
            local_pkg = self.local_db.get_package(name)
        return local_pkg["id"] if local_pkg else None

    # ------------------------------------------------------------------
    # Kurulum
    # ------------------------------------------------------------------

    def install_files(self, deb_paths, reasons=None, action="install"):
        """
        Yerel .deb dosyalarını kurar.

        reasons: {paket_adı: "explicit" | "dependency"}
        action : "install" veya "update" (geçmiş kaydı için)
        Dönüş   : [{"name": ..., "version": ...}, ...]
        """
        self.require_root()
        reasons = reasons or {}
        deb_paths = list(deb_paths)
        if not deb_paths:
            return []

        # 1) .deb bütünlük kontrolü (bozuk dosya tespiti)
        for path in deb_paths:
            ok, msg = security.verify_deb(path)
            if not ok:
                raise InstallError(
                    "%s kurulamadı: %s" % (os.path.basename(path), msg))

        # 2) bağımlılıklar çözücü tarafından zaten kontrol edildi
        ui.info("🔍 Bağımlılıklar kontrol edildi ✓")

        # 3) hook'lar: pre-install / pre-upgrade
        for path in deb_paths:
            meta = self._deb_meta(path)
            self._run_hooks("pre", action, meta.get("Package", ""),
                            meta.get("Version"))

        # 4) dpkg -i (tüm paketler tek seferde → grup içi bağımlılıklar çözülür)
        with ui.spinner("📦 Paketler açılıyor ve yapılandırılıyor..."):
            proc = self._run_dpkg(["-i"] + deb_paths)
        if proc.returncode != 0:
            self.local_db.add_history(action, "(grup)", None, None, False)
            raise InstallError(self._friendly_error(proc))

        # 5) kayıtlar: yerel db, geçmiş, indirme sayacı, hook'lar
        installed_now = []
        for path in deb_paths:
            meta = self._deb_meta(path)
            name = meta.get("Package") or os.path.basename(path)
            version = meta.get("Version", "?")
            old = self.local_db.get_installed(name)
            files = self.files_of(name)
            self.local_db.add_installed(
                name=name, version=version, package_id=self._local_pkg_id(name),
                reason=reasons.get(name, "explicit"), files=files)
            self.local_db.add_history(
                action, name,
                old["version"] if (action == "update" and old) else None,
                version, True)
            self.sync_db.record_download(name)
            self._run_hooks("post", action, name, version)
            installed_now.append({"name": name, "version": version})
        return installed_now

    # ------------------------------------------------------------------
    # Kaldırma
    # ------------------------------------------------------------------

    def remove(self, names, purge=False, recursive=False):
        """
        Paket(ler)i kaldırır.

        purge     : -Rns → yapılandırma dosyalarıyla birlikte (dpkg --purge)
        recursive : -Rs  → kaldırılan paketlerin artık gereği kalmayan
                    bağımlılıklarını da kaldırır
        """
        self.require_root()
        removed = []
        for name in dict.fromkeys(names):
            installed = (self.local_db.is_installed(name)
                         or self._system_installed(name))
            if not installed:
                ui.warning("%s kurulu değil, atlanıyor." % ui.pkg(name))
                continue
            old = self.local_db.get_installed(name)
            self._run_hooks("pre", "remove", name,
                            old["version"] if old else None)
            with ui.spinner("🗑️  %s kaldırılıyor..." % name):
                proc = self._run_dpkg(
                    ["--purge" if purge else "--remove", name])
            if proc.returncode != 0:
                raise InstallError(self._friendly_error(proc))
            self.local_db.remove_installed(name)
            self.local_db.add_history(
                "remove", name, old["version"] if old else None, None, True)
            self._run_hooks("post", "remove", name,
                            old["version"] if old else None)
            removed.append(name)
            ui.success("%s kaldırıldı." % ui.pkg(name))

        # -Rs: gereksiz bağımlılıkları de kaldır
        if recursive and removed:
            orphans = Resolver(
                self.sync_db, self.local_db,
                self.config.architecture).find_orphans()
            for orphan in orphans:
                if orphan["name"] not in removed:
                    self.remove([orphan["name"]], purge=purge, recursive=False)
        return removed

    # ------------------------------------------------------------------
    # Geri alma (rollback)
    # ------------------------------------------------------------------

    def rollback(self, history_id):
        """Geçmişteki bir işlemi geri alır."""
        self.require_root()
        entry = self.local_db.get_history_entry(history_id)
        if not entry:
            raise InstallError(
                "#%s numaralı geçmiş kaydı bulunamadı." % history_id)
        action = entry["action"]
        name = entry["package_name"]

        if action == "install":
            # kurulumu geri al → paketi kaldır
            ui.info("#%s geri alınıyor: %s kaldırılacak"
                    % (history_id, name))
            return {"action": "install→remove",
                    "packages": self.remove([name])}

        if action in ("remove", "update"):
            # kaldırmayı/güncellemeyi geri al → eski sürümü yeniden kur
            version = entry.get("from_version")
            pkg = self.sync_db.get_package(name)
            if not pkg or (version and pkg["version"] != version):
                raise InstallError(
                    "%s %s sürümü depoda bulunamadı; geri alınamıyor."
                    % (name, version or ""))
            ui.info("#%s geri alınıyor: %s %s yeniden kuruluyor"
                    % (history_id, name, version))
            path = self._obtain_deb(pkg)
            self.install_files([path], reasons={name: "explicit"},
                               action="install")
            return {"action": "%s→reinstall" % action, "packages": [name]}

        raise InstallError("%s işlemi geri alınamıyor." % action)

    def _obtain_deb(self, pkg):
        """Paketin .deb dosyasını önbellekten veya depodan bulur/indirir."""
        self.cache.ensure()
        cached = self.cache.path_for(pkg["filename"])
        if os.path.isfile(cached):
            ok, _msg = security.verify_checksums(
                cached, pkg.get("sha256"), pkg.get("md5sum"))
            if ok:
                return cached
        if not self.downloader:
            raise InstallError("indirme motoru yok; .deb bulunamadı.")
        repo = self.local_db.get_repo(pkg.get("repo") or "deox")
        if not repo:
            raise InstallError(
                "'%s' deposu tanımlı değil." % pkg.get("repo"))
        url = (repo["url"].rstrip("/") + "/deoxpool/" + pkg["filename"])
        item = DownloadItem(pkg["name"], url, self.cache.pkg_dir,
                            pkg["filename"], pkg.get("sha256"),
                            pkg.get("size"), pkg.get("md5sum"))
        return self.downloader.download(item)

    # ------------------------------------------------------------------
    # Sorgular
    # ------------------------------------------------------------------

    def _system_installed(self, name):
        """Paket sistemde (deox dışı) kurulu mu?"""
        rc, out, _ = utils.run_cmd(
            ["dpkg-query", "-W", "-f=${Status}", name])
        return rc == 0 and "installed" in out

    def files_of(self, name):
        """Paketin kurduğu dosyaların listesi (dpkg-query -L)."""
        cmd = ["dpkg-query"]
        if self.test_mode:
            cmd.append("--admindir=%s" % os.path.join(
                self.paths["rootfs"], "var/lib/dpkg"))
        cmd += ["-L", name]
        rc, out, _ = utils.run_cmd(cmd)
        if rc != 0:
            return []
        return [l.strip() for l in out.splitlines()
                if l.strip() and not l.startswith("/var/lib/dpkg")]

    def owner_of(self, path):
        """Verilen dosyanın sahibi paketin adını döndürür (yoksa None)."""
        cmd = ["dpkg-query"]
        if self.test_mode:
            cmd.append("--admindir=%s" % os.path.join(
                self.paths["rootfs"], "var/lib/dpkg"))
        cmd += ["-S", os.path.abspath(path)]
        rc, out, _ = utils.run_cmd(cmd)
        if rc != 0 or not out:
            return None
        first = out.splitlines()[0]
        return first.split(":")[0].strip() or None

    # ------------------------------------------------------------------
    # Hook sistemi
    # ------------------------------------------------------------------

    def _run_hooks(self, phase, action, name, version):
        """
        /etc/deox/hooks.d altındaki pre/post-install/remove/upgrade
        scriptlerini çalıştırır.

        Aranan adlar: "<phase>-<action>" veya "<phase>-<action>.sh"
        (ayrıca aynı isimli bir dizin varsa içindeki tüm çalıştırılabilirler).
        Ortam değişkenleri: DEOX_PHASE, DEOX_ACTION, DEOX_PACKAGE, DEOX_VERSION
        """
        hooks_dir = self.paths["hooks"]
        if not os.path.isdir(hooks_dir):
            return
        hook_name = "%s-%s" % (phase, action)
        env = dict(os.environ)
        env.update({
            "DEOX_PHASE": phase,
            "DEOX_ACTION": action,
            "DEOX_PACKAGE": name or "",
            "DEOX_VERSION": version or "",
        })
        scripts = []
        for entry in sorted(os.listdir(hooks_dir)):
            path = os.path.join(hooks_dir, entry)
            base = entry[:-3] if entry.endswith(".sh") else entry
            if base == hook_name:
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    scripts.append(path)
                elif os.path.isdir(path):
                    scripts.extend(
                        sorted(os.path.join(path, s)
                               for s in os.listdir(path)
                               if os.access(os.path.join(path, s), os.X_OK)))
        for script in scripts:
            utils.LOGGER.info("hook çalıştırılıyor: %s (%s-%s %s)",
                              script, phase, action, name)
            try:
                if ui.JSON_MODE:
                    # JSON kipinde stdout temiz tutulur; çıktı log'a yazılır
                    proc = subprocess.run([script], env=env, capture_output=True,
                                          text=True, timeout=120)
                    if proc.stdout:
                        utils.LOGGER.info("hook %s stdout: %s",
                                          os.path.basename(script),
                                          proc.stdout.strip())
                else:
                    # normal kipte hook çıktısı terminale akar
                    proc = subprocess.run([script], env=env, timeout=120)
                if proc.returncode != 0:
                    ui.warning("hook %s hata verdi (kod %d)"
                               % (os.path.basename(script), proc.returncode))
            except (OSError, subprocess.SubprocessError) as exc:
                ui.warning("hook %s çalıştırılamadı: %s"
                           % (os.path.basename(script), exc))

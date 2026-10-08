# -*- coding: utf-8 -*-
"""
DEOX bağımlılık çözücü.

Repo veritabanındaki "depends" bilgilerini kullanarak kurulum planı çıkarır:
  - hangi paketlerin kurulacağı (bağımlılık öncelikli sırada)
  - hangileri zaten kurulu (deox veya sistem/dpkg ile)
  - hangileri depoda yok
  - sürüm kısıtları, alternatifler (foo | bar) ve çakışmalar (conflicts)
  - sanal paketler (provides) üzerinden çözümleme

Ayrıca şunları da üretir:
  - find_upgrades : kurulu paketler için yeni sürümler
  - find_orphans  : artık gereği kalmamış bağımlılık paketleri
"""

from . import utils


class ResolveError(utils.DeoxError):
    """Bağımlılık çözülemedi."""


class InstallPlan:
    """Çözücü tarafından üretilen kurulum planı."""

    def __init__(self):
        self.to_install = []         # kurulacak paketler (sırayla) [dict]
        self.already_installed = []  # zaten kurulu olanlar [name]
        self.missing = []            # depoda bulunamayanlar [name]
        self.conflicts = []          # çakışma açıklamaları [str]
        self.warnings = []           # uyarılar [str]
        self.reasons = {}            # {paket_adı: "explicit" | "dependency"}

    @property
    def total_download(self):
        """Toplam indirme boyutu (bayt)."""
        return sum(p.get("size") or 0 for p in self.to_install)

    @property
    def total_installed_size(self):
        """Toplam kurulu boyut (bayt)."""
        return sum(p.get("installed_size") or 0 for p in self.to_install)

    def names(self):
        """Kurulacak paket adları."""
        return [p["name"] for p in self.to_install]

    def to_dict(self):
        """JSON-uyumlu sözlük."""
        return {
            "to_install": self.to_install,
            "already_installed": self.already_installed,
            "missing": self.missing,
            "conflicts": self.conflicts,
            "warnings": self.warnings,
            "reasons": self.reasons,
            "total_download": self.total_download,
            "total_installed_size": self.total_installed_size,
        }


class Resolver:
    """Depo + sistem verisiyle bağımlılık çözen sınıf."""

    def __init__(self, sync_db, local_db, arch=None):
        self.sync_db = sync_db
        self.local_db = local_db
        self.arch = arch or utils.detect_architecture()

    # ------------------------------------------------------------------
    # Yardımcı sorgular
    # ------------------------------------------------------------------

    def _system_version(self, name):
        """dpkg-query ile sistemdeki paketin sürümünü döndürür (yoksa None)."""
        rc, out, _ = utils.run_cmd(
            ["dpkg-query", "-W", "-f=${Status} ${Version}", name])
        if rc != 0:
            return None
        parts = out.strip().split(" ", 1)
        if len(parts) < 2 or "installed" not in parts[0]:
            return None
        return parts[1]

    def _installed_version(self, name):
        """Paket deox ile mi kurulu? Sürümünü döndürür."""
        inst = self.local_db.get_installed(name)
        return inst["version"] if inst else None

    def _version_ok(self, installed_version, op, wanted):
        """Sürüm kısıtını denetler."""
        if not op or not wanted:
            return True
        return utils.compare_versions(installed_version, op, wanted)

    def _find_candidate(self, dep_name):
        """Depodaki paketi bulur; mimari uyumu: tam eşleşme veya 'all'."""
        pkg = self.sync_db.get_package(dep_name)
        if pkg and pkg["architecture"] in (self.arch, "all"):
            return pkg
        return None

    def _dep_groups(self, pkg_name, dep_type):
        """Bir paketin bağımlılık gruplarını ayrıştırır (alternatiflerle)."""
        groups = []
        for row in self.sync_db.deps_of(pkg_name, dep_type=dep_type):
            parsed = utils.parse_depends(row["dep_name"])
            if parsed:
                groups.append(parsed[0])
        return groups

    def _resolve_alternative(self, alternatives, visiting):
        """
        'foo | bar' alternatiflerinden uygun olanı seçer.
        Dönüş: (kind, name, version) — kind: "system" | "local" | "repo"
        """
        for dep_name, op, ver in alternatives:
            # 1) sistemde kurulu mu?
            sys_ver = self._system_version(dep_name)
            if sys_ver and self._version_ok(sys_ver, op, ver):
                return ("system", dep_name, sys_ver)
            # 2) deox ile kurulu mu?
            local_ver = self._installed_version(dep_name)
            if local_ver and self._version_ok(local_ver, op, ver):
                return ("local", dep_name, local_ver)
            # 3) depoda var mı?
            pkg = self._find_candidate(dep_name)
            if pkg and self._version_ok(pkg["version"], op, ver):
                return ("repo", pkg["name"], pkg["version"])
            # 4) sanal paket: provides eden var mı?
            for provider in self.sync_db.providers_of(dep_name):
                if (provider["architecture"] in (self.arch, "all")
                        and provider["name"] not in visiting):
                    return ("repo", provider["name"], provider["version"])
        return None

    # ------------------------------------------------------------------
    # Kurulum planı
    # ------------------------------------------------------------------

    def resolve(self, names, include_recommends=False, upgrade=False):
        """
        Verilen paket adları için kurulum planı üretir.

        upgrade=True ise, kurulu olup depoda daha yeni sürümü bulunan
        paketler plana dahil edilir (deox -Su için).
        """
        plan = InstallPlan()
        visiting = set()  # döngüsel bağımlılık koruması

        def visit(name, reason="explicit"):
            if name in plan.names():
                # daha önce bağımlılık olarak eklenmiş, şimdi açık isteniyor
                if reason == "explicit":
                    plan.reasons[name] = "explicit"
                return
            if name in plan.already_installed:
                return
            if name in visiting:
                plan.warnings.append("döngüsel bağımlılık: %s" % name)
                return

            sys_ver = self._system_version(name)
            local_ver = self._installed_version(name)
            installed_ver = sys_ver or local_ver

            if installed_ver and not upgrade:
                plan.already_installed.append(name)
                return

            pkg = self._find_candidate(name)
            if pkg is None:
                # sanal paket: provides eden var mı?
                providers = self.sync_db.providers_of(name)
                if providers:
                    pkg = providers[0]
                else:
                    plan.missing.append(name)
                    return

            # kurulu sürüm depodan yeniyse düşürme yapma
            if installed_ver and utils.compare_versions(
                    installed_ver, ">>", pkg["version"]):
                plan.warnings.append(
                    "%s: kurulu sürüm (%s) depodakinden (%s) yeni, atlanıyor"
                    % (name, installed_ver, pkg["version"]))
                plan.already_installed.append(name)
                return

            visiting.add(pkg["name"])

            # conflicts kontrolü
            for group in self._dep_groups(pkg["name"], "conflicts"):
                for dep_name, _op, _ver in group:
                    if (self._system_version(dep_name)
                            or self.local_db.is_installed(dep_name)):
                        plan.conflicts.append(
                            "%s ↔ %s (conflicts)" % (pkg["name"], dep_name))

            # depends: her grup için uygun alternatifi çöz
            for group in self._dep_groups(pkg["name"], "depends"):
                choice = self._resolve_alternative(group, visiting)
                if choice is None:
                    plan.missing.append(group[0][0])
                    continue
                kind, dep_name, _ver = choice
                if kind == "repo":
                    visit(dep_name, reason="dependency")

            # recommends: istenirse çöz
            if include_recommends:
                for group in self._dep_groups(pkg["name"], "recommends"):
                    choice = self._resolve_alternative(group, visiting)
                    if choice and choice[0] == "repo":
                        visit(choice[1], reason="dependency")

            visiting.discard(pkg["name"])
            if pkg["name"] not in plan.names():
                plan.to_install.append(pkg)
                plan.reasons[pkg["name"]] = reason

        for name in names:
            visit(name, "explicit")

        # yinelenenleri temizle, sırayı koru
        plan.already_installed = list(dict.fromkeys(plan.already_installed))
        plan.missing = list(dict.fromkeys(plan.missing))
        return plan

    # ------------------------------------------------------------------
    # Güncelleme ve yetim analizi
    # ------------------------------------------------------------------

    def find_upgrades(self):
        """Kurulu paketlerin depodaki daha yeni sürümlerini listeler."""
        upgrades = []
        for inst in self.local_db.get_installed():
            pkg = self.sync_db.get_package(inst["name"])
            if not pkg:
                continue
            if utils.compare_versions(pkg["version"], ">>", inst["version"]):
                upgrades.append({
                    "name": inst["name"],
                    "installed_version": inst["version"],
                    "available_version": pkg["version"],
                    "size": pkg.get("size"),
                    "repo": pkg.get("repo", "deox"),
                })
        return upgrades

    def find_orphans(self):
        """
        Hiçbir 'explicit' paket tarafından gerektirilmeyen, bağımlılık
        olarak kurulmuş paketleri bulur (deox -Rs / --clean-orphans için).
        """
        installed = {i["name"]: i for i in self.local_db.get_installed()}
        needed = set()

        def mark(name):
            if name in needed or name not in installed:
                return
            needed.add(name)
            for group in self._dep_groups(name, "depends"):
                for dep_name, _op, _ver in group:
                    if (self._system_version(dep_name)
                            or dep_name in installed):
                        mark(dep_name)

        for name, inst in installed.items():
            if inst.get("install_reason") == "explicit":
                mark(name)

        return [inst for name, inst in installed.items()
                if name not in needed
                and inst.get("install_reason") == "dependency"]

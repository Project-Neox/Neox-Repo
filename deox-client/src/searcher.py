# -*- coding: utf-8 -*-
"""
DEOX paket arama ve bilgi modülü.

- search_remote   : depoda paket ara (deox -Ss)
- search_installed: kurulu paketlerde ara (deox -Qs)
- info            : paket detayları (deox -Si / -Qi)

Tüm yöntemler sözlük listesi döndürür; terminale yazdırma işi main/ui katmanına
aittir (böylece --json kipinde aynı veri JSON olarak çıkar).
"""

from . import utils


class Searcher:
    """Sync ve local veritabanları üzerinde arama/bilgi sorguları."""

    def __init__(self, sync_db, local_db, arch=None):
        self.sync_db = sync_db
        self.local_db = local_db
        self.arch = arch

    def _arch_ok(self, pkg):
        """Paket hedef mimariyle uyumlu mu? (tam eşleşme veya 'all')"""
        return not self.arch or pkg["architecture"] in (self.arch, "all")

    def _system_installed(self, name):
        """Paket sistemde (deox dışı) kurulu mu?"""
        rc, out, _ = utils.run_cmd(["dpkg-query", "-W", "-f=${Status}", name])
        return rc == 0 and "installed" in out

    def search_remote(self, keyword, limit=50):
        """Depoda paket arar; sonuçlara kurulu bilgisi eklenir."""
        results = []
        for pkg in self.sync_db.search(keyword, limit=limit):
            if not self._arch_ok(pkg):
                continue
            inst = self.local_db.get_installed(pkg["name"])
            results.append({
                **pkg,
                "installed": bool(inst) or self._system_installed(pkg["name"]),
                "installed_version": inst["version"] if inst else None,
            })
        return results

    def search_installed(self, keyword, limit=50):
        """Kurulu paketlerde ada göre arar."""
        out = []
        keyword = (keyword or "").lower()
        for inst in self.local_db.get_installed():
            if (keyword in inst["name"].lower()
                    or keyword in (inst.get("version") or "").lower()):
                pkg = self.sync_db.get_package(inst["name"]) or {}
                out.append({**pkg, **inst, "installed": True})
                if len(out) >= limit:
                    break
        return out

    def info(self, name):
        """
        Paket detaylarını döndürür.

        Depoda yoksa ama sistemde kuruluysa yerel bilgiyle döner;
        hiçbir yerde yoksa None döner. Sanal paket ise sağlayıcıları döndürür.
        """
        pkg = self.sync_db.get_package(name)
        inst = self.local_db.get_installed(name)

        if pkg is None:
            if inst or self._system_installed(name):
                return {"name": name, "found": True, "in_repo": False,
                        "installed": True, **inst}
            providers = self.sync_db.providers_of(name)
            if providers:
                return {"name": name, "found": False, "providers": providers}
            return None

        deps = {}
        for dep_type in ("depends", "recommends", "suggests", "conflicts",
                         "replaces", "provides"):
            deps[dep_type] = self.sync_db.deps_of(name, dep_type=dep_type)

        return {
            **pkg,
            "dependencies": deps,
            "installed": bool(inst),
            "installed_version": inst["version"] if inst else None,
            "found": True,
            "in_repo": True,
        }

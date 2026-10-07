#!/usr/bin/env python3
"""Derlenmis deponun Packages dosyasindan GitHub Pages sitesi icin
packages.json uretir (site bu dosyayi okuyup paket listesini gosterir).

Kullanim: make-packages-json.py [STAGING_DIR]   (varsayilan: public/)
"""
import json
import os
import sys
from datetime import datetime, timezone

SUITE = os.environ.get("NEOX_SUITE", "stable")
COMPONENT = os.environ.get("NEOX_COMPONENT", "main")
ARCH = os.environ.get("NEOX_ARCH", "amd64")
REPO_URL = os.environ.get("NEOX_REPO_URL", "https://project-neox.github.io/Neox-Repo")


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def parse_packages(path: str):
    packages = []
    stanza = {}
    last_key = None

    def flush():
        if stanza.get("Package"):
            packages.append(stanza)

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                flush()
                stanza = {}
                last_key = None
                continue
            if line[0] in (" ", "\t") and last_key:
                stanza[last_key] += "\n" + line.strip()
            elif ":" in line:
                key, value = line.split(":", 1)
                last_key = key
                stanza[key] = value.strip()
    flush()
    return packages


def main() -> int:
    staging = sys.argv[1] if len(sys.argv) > 1 else "public"
    packages_path = os.path.join(
        staging, "dists", SUITE, COMPONENT, f"binary-{ARCH}", "Packages"
    )
    if not os.path.isfile(packages_path):
        print(f"HATA: {packages_path} bulunamadi", file=sys.stderr)
        return 1

    entries = []
    for p in parse_packages(packages_path):
        size = int(p.get("Size", 0))
        entries.append(
            {
                "name": p.get("Package", ""),
                "version": p.get("Version", ""),
                "architecture": p.get("Architecture", ""),
                "section": p.get("Section", ""),
                "priority": p.get("Priority", ""),
                "maintainer": p.get("Maintainer", ""),
                "size": size,
                "size_human": human_size(size),
                "sha256": p.get("SHA256", ""),
                "filename": p.get("Filename", ""),
                "description": " ".join(
                    line.strip()
                    for line in p.get("Description", "").splitlines()
                    if line.strip() and line.strip() != "."
                ),
                "install_command": f"sudo apt install {p.get('Package', '')}",
            }
        )
    entries.sort(key=lambda e: e["name"])

    doc = {
        "name": "Neox APT Repository",
        "url": REPO_URL,
        "suite": SUITE,
        "component": COMPONENT,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(entries),
        "packages": entries,
    }

    out = os.path.join(staging, "packages.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"packages.json yazildi: {out} ({len(entries)} paket)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

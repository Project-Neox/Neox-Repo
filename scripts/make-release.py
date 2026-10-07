#!/usr/bin/env python3
"""apt-ftparchive bulunmayan ortamlarda Release dosyasi uretir.

Kullanim: make-release.py <dists/stable>
Release dosyasi; dizin icindeki tum dosyalarin MD5/SHA1/SHA256/SHA512
checksum'larini icerir (apt-ftparchive ile ayni format).
"""
import hashlib
import os
import sys
from email.utils import formatdate
from time import time


def main() -> int:
    dist_dir = sys.argv[1]
    origin = os.environ.get("NEOX_ORIGIN", "Neox")
    label = os.environ.get("NEOX_LABEL", "Neox-Repo")
    suite = os.environ.get("NEOX_SUITE", "stable")
    component = os.environ.get("NEOX_COMPONENT", "main")
    arch = os.environ.get("NEOX_ARCH", "amd64")
    description = os.environ.get("NEOX_DESCRIPTION", "Neox APT Repository - Project-Neox")

    skip = {"Release", "InRelease", "Release.gpg"}
    files = []
    for base, _, names in os.walk(dist_dir):
        for name in sorted(names):
            if name in skip:
                continue
            full = os.path.join(base, name)
            files.append(os.path.relpath(full, dist_dir))
    files.sort()

    lines = [
        f"Origin: {origin}",
        f"Label: {label}",
        f"Suite: {suite}",
        f"Codename: {suite}",
        f"Architectures: {arch}",
        f"Components: {component}",
        f"Description: {description}",
        f"Date: {formatdate(time(), usegmt=True)}",
    ]

    for algo, field in (
        ("md5", "MD5Sum"),
        ("sha1", "SHA1"),
        ("sha256", "SHA256"),
        ("sha512", "SHA512"),
    ):
        lines.append(f"{field}:")
        for rel in files:
            with open(os.path.join(dist_dir, rel), "rb") as f:
                data = f.read()
            digest = hashlib.new(algo, data).hexdigest()
            lines.append(f" {digest} {len(data)} {rel}")

    out = os.path.join(dist_dir, "Release")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Release yazildi: {out} ({len(files)} dosya checksumlandi)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

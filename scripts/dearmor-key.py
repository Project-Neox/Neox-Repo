#!/usr/bin/env python3
"""Armored (.asc) OpenPGP anahtarindan binary (.gpg) anahtar uretir.

Kullanim: dearmor-key.py <giris.asc> <cikis.gpg>
Hedef sistemde `gpg --dearmor` komutu gerektirmez (apt'nin keyring'i binary olmalidir).
"""
import base64
import sys


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("-----BEGIN"))
    except StopIteration:
        print("HATA: armor baslik bulunamadi", file=sys.stderr)
        return 1

    i = start + 1
    # Armor header'larini (Version:, Comment: ...) atla - ilk bos satira kadar
    while i < len(lines) and lines[i].strip():
        i += 1
    i += 1  # bos satiri da atla

    body = []
    for line in lines[i:]:
        if line.startswith("=") or line.startswith("-----END"):
            break
        if line.strip():
            body.append(line.strip())

    data = base64.b64decode("".join(body))
    with open(dst, "wb") as f:
        f.write(data)
    print(f"Dearmor: {src} -> {dst} ({len(data)} bayt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

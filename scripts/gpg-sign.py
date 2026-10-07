#!/usr/bin/env python3
"""gpg komutu bulunmayan ortamlarda Release dosyasini pgpy ile imzalar.

Kullanim:  NEOX_GPG_KEY_FILE=/path/private.asc python3 gpg-sign.py <dists/stable>/Release

Cikti:
  <dists/stable>/InRelease   (clearsigned - apt'nin tercih ettigi format)
  <dists/stable>/Release.gpg (armored detached imza - yedek format)
"""
import os
import sys

import pgpy
from pgpy.constants import HashAlgorithm


def main() -> int:
    release_path = sys.argv[1]
    key_file = os.environ.get("NEOX_GPG_KEY_FILE")
    if not key_file:
        print("HATA: NEOX_GPG_KEY_FILE ortam degiskeni gerekli", file=sys.stderr)
        return 1

    key, _ = pgpy.PGPKey.from_file(key_file)
    if key.is_public:
        print("HATA: ozel anahtar gerekli (public key ile imza atilamaz)", file=sys.stderr)
        return 1

    dist_dir = os.path.dirname(release_path)

    with open(release_path, "r", encoding="utf-8") as f:
        text = f.read()

    # InRelease: clearsigned
    msg = pgpy.PGPMessage.new(text, cleartext=True)
    msg |= key.sign(msg, hash=HashAlgorithm.SHA256)
    with open(os.path.join(dist_dir, "InRelease"), "w", encoding="utf-8") as f:
        f.write(str(msg))

    # Release.gpg: detached binary imza
    with open(release_path, "rb") as f:
        data = f.read()
    sig = key.sign(data, hash=HashAlgorithm.SHA256)
    with open(os.path.join(dist_dir, "Release.gpg"), "wb") as f:
        f.write(bytes(sig))

    print(f"Imzalandi (key: {key.fingerprint.keyid}): InRelease + Release.gpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())

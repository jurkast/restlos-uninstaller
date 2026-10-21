#!/usr/bin/env python3
"""Signiertes Update-Manifest (restlos-update.json/.sig) für ein gebautes Release erzeugen.

Aufruf: sign_update.py DIST_ORDNER PRIVATER_SCHLÜSSEL
Der private Ed25519-Schlüssel muss außerhalb des Projektordners liegen (im CI: GitHub-Secret
RESTLOS_SIGNING_KEY, nur als temporäre Datei vorhanden).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from restlos.updater import APPLICATION, MANIFEST_NAME, PUBLIC_KEY_NAME, SIGNATURE_NAME, version_of  # noqa: E402

# Erste Version mit dem signierten Startverfahren; ältere Installationen benötigen einmalig
# eine manuelle Installation.
MINIMUM_BASE = "2.1.0"


def main(arguments: list[str]) -> int:
    if len(arguments) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    dist, key = Path(arguments[0]).resolve(), Path(arguments[1]).resolve()
    if key.is_relative_to(ROOT):
        raise SystemExit("Der private Signierschlüssel muss außerhalb des Projektordners liegen.")
    version = version_of(ROOT)
    archive = dist / f"Restlos-{version}.tar.gz"
    if not archive.is_file():
        raise SystemExit(f"Release-Archiv fehlt: {archive}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {
        "application": APPLICATION,
        "architecture": "all",
        "version": version,
        "minimum_base": MINIMUM_BASE,
        "archive": archive.name,
        "size": archive.stat().st_size,
        "sha256": digest,
    }
    manifest_path = dist / MANIFEST_NAME
    signature_path = dist / SIGNATURE_NAME
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["openssl", "pkeyutl", "-sign", "-inkey", str(key), "-rawin",
                    "-in", str(manifest_path), "-out", str(signature_path)], check=True)
    # Gegenprobe mit dem öffentlichen Schlüssel, den die Programme mitbringen: ein falsches
    # Secret fällt hier auf statt erst bei den Nutzern.
    check = subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(ROOT / "restlos" / PUBLIC_KEY_NAME),
                            "-rawin", "-in", str(manifest_path), "-sigfile", str(signature_path)],
                           capture_output=True, check=False)
    if check.returncode != 0:
        signature_path.unlink(missing_ok=True)
        raise SystemExit("Der Signierschlüssel passt nicht zu restlos/update-public.pem – "
                         "RESTLOS_SIGNING_KEY muss derselbe Schlüssel wie bei Restlos Bewerbung sein.")
    print(f"Signiertes Update-Manifest für {version}: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

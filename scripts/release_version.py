#!/usr/bin/env python3
"""Version an allen Stellen gleichzeitig lesen oder setzen.

  release_version.py current          → aktuelle Version ausgeben
  release_version.py next-patch       → nächste Patch-Version ausgeben (2.1.0 → 2.1.1)
  release_version.py set 2.2.0 [TEXT] → Version überall setzen, Debian-Changelog ergänzen
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"\d+\.\d+\.\d+")
MAINTAINER = "jurkast <312310339+jurkast@users.noreply.github.com>"


def current() -> str:
    text = (ROOT / "restlos/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', text, re.MULTILINE)
    if match is None or not VERSION.fullmatch(match.group(1)):
        raise SystemExit("Version in restlos/__init__.py nicht lesbar.")
    return match.group(1)


def next_patch(version: str) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def _replace(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"Versionszeile nicht gefunden: {path.relative_to(ROOT)}")
    path.write_text(updated, encoding="utf-8")


def set_version(version: str, note: str) -> None:
    if not VERSION.fullmatch(version):
        raise SystemExit(f"Ungültige Version: {version}")
    _replace(ROOT / "restlos/__init__.py", r'^__version__ = "[^"]+"$', f'__version__ = "{version}"')
    _replace(ROOT / "pyproject.toml", r'^version = "[^"]+"$', f'version = "{version}"')
    _replace(ROOT / "snap/snapcraft.yaml", r'^version: "[^"]+"$', f'version: "{version}"')
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changelog = ROOT / "debian/changelog"
    text = changelog.read_text(encoding="utf-8")
    if not text.startswith(f"restlos-uninstaller ({version}-"):
        stamp = format_datetime(datetime.now(timezone.utc).astimezone())
        entry = (
            f"restlos-uninstaller ({version}-1ppa1) UNRELEASED; urgency=medium\n\n"
            f"  * {note}\n\n -- {MAINTAINER}  {stamp}\n\n"
        )
        changelog.write_text(entry + text, encoding="utf-8")


def main(arguments: list[str]) -> int:
    match arguments:
        case ["current"]:
            print(current())
        case ["next-patch"]:
            print(next_patch(current()))
        case ["set", version]:
            set_version(version, "Automatic release with fixes and improvements.")
        case ["set", version, note]:
            set_version(version, note)
        case _:
            print(__doc__, file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

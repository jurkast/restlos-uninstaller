"""Verwaiste Programmdaten finden: Ordner von Programmen, die nicht mehr installiert sind.

Nur lesend. Ein Fund ist ein Vorschlag zur Prüfung, kein Löschziel: Entfernt wird ausschließlich
über den normalen, versiegelten Löschplan (Papierkorb, Safety Backup, Schutzprüfung).
"""
from __future__ import annotations

import re
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .analyzer import RemovalAnalyzer
from .models import AppRecord, SourceKind
from .package_managers import PACKAGE_ID_PATTERN, _trusted_binary
from .utils import normalize_key, path_size, run_command


@dataclass(frozen=True, slots=True)
class Leftover:
    path: Path
    reason: str
    size: int
    modified: float


# Gemeinsame Desktop-, System- und Bibliotheksordner – gehören keinem einzelnen Programm.
_IGNORED_NAMES = frozenset(normalize_key(name) for name in (
    "applications", "autostart", "backgrounds", "dconf", "enchant", "environment.d", "fontconfig", "fonts",
    "glib-2.0", "goa-1.0", "gtk-2.0", "gtk-3.0", "gtk-4.0", "gvfs-metadata", "ibus", "icons", "keyrings",
    "menus", "mime", "nautilus", "pulse", "pipewire", "wireplumber", "session", "sessions", "sounds",
    "systemd", "themes", "thumbnails", "Trash", "tracker", "tracker3", "xdg-desktop-portal", "dbus-1",
    "update-notifier", "user-dirs", "evolution", "folks", "geoclue", "telepathy", "gstreamer-1.0",
    "mesa_shader_cache", "mesa_shader_cache_db", "radv_builtin_shaders", "nvidia", "nv", "vulkan",
    "event-sound-cache", "webkitgtk", "babl", "gegl-0.4", "ksycoca", "kwalletd", "qtshadercache",
    "pip", "pypoetry", "virtualenv", "jedi", "matplotlib", "node-gyp", "npm", "yarn", "go-build",
    "configstore", "flatpak", "snap", "restlos", "restlos-uninstaller-updates", "restlos-bewerbung-updates",
    "recently-used.xbel", "obexd", "libvirt", "speech-dispatcher", "orca", "xsettingsd", "kvantum",
    "qt5ct", "qt6ct", "gnupg", "ssh", "containers", "doc", "desktop-directories", "kxmlgui5",
))
_IGNORED_PREFIXES = tuple(normalize_key(name) for name in (
    "gnome", "gtk", "kde", "plasma", "kf5", "kf6", "xfce", "cinnamon", "mate", "lxqt", "lxsession", "zorin",
    "ubuntu", "canonical", "fcitx", "qtshader", "mesa", "restlos",
))


class LeftoverScanner:
    def __init__(
        self,
        home: Path | None = None,
        *,
        installed_packages: Callable[[], set[str]] | None = None,
        which: Callable[[str], str | None] = shutil.which,
        flatpak_ids: Callable[[], set[str] | None] | None = None,
        snap_names: Callable[[], set[str] | None] | None = None,
    ) -> None:
        self.home = (home or Path.home()).absolute()
        self._installed_packages = installed_packages or _installed_package_names
        self._which = which
        self._flatpak_ids = flatpak_ids or _flatpak_ids
        self._snap_names = snap_names or _snap_names
        self._analyzer = RemovalAnalyzer(self.home)

    def scan(self, applications: Iterable[AppRecord]) -> list[Leftover]:
        applications = list(applications)
        aliases: set[str] = set()
        for app in applications:
            aliases |= self._analyzer._aliases(app)
        packages = {normalize_key(name) for name in self._installed_packages()}
        flatpaks = {app.package_id for app in applications if app.source == SourceKind.FLATPAK}
        snaps = {app.package_id for app in applications if app.source == SourceKind.SNAP}
        found: list[Leftover] = []

        sandbox = self.home / ".var/app"
        # Nur wenn die Paketliste sicher gelesen wurde – sonst wäre jeder Ordner ein „Rest“.
        flatpak_ids = self._flatpak_ids()
        if flatpak_ids is not None:
            flatpak_known = flatpak_ids | flatpaks
            for path in _children(sandbox):
                if path.name not in flatpak_known and PACKAGE_ID_PATTERN.fullmatch(path.name):
                    found.append(_leftover(path, "Flatpak ist nicht mehr installiert"))

        snap_root = self.home / "snap"
        snap_names = self._snap_names()
        if snap_names is not None:
            snap_known = snap_names | snaps
            for path in _children(snap_root):
                if path.name not in snap_known and PACKAGE_ID_PATTERN.fullmatch(path.name):
                    found.append(_leftover(path, "Snap ist nicht mehr installiert"))

        for relative in (".config", ".local/share", ".cache", ".local/state"):
            for path in _children(self.home / relative):
                if self._belongs_to_something(path.name, aliases, packages):
                    continue
                found.append(_leftover(path, "Kein installiertes Programm gefunden – bitte prüfen"))
        return sorted(found, key=lambda item: (-item.size, str(item.path)))

    def _belongs_to_something(self, name: str, aliases: set[str], packages: set[str]) -> bool:
        key = normalize_key(name)
        if len(key) < 3 or key in _IGNORED_NAMES or key.startswith(_IGNORED_PREFIXES):
            return True
        if key in packages or key in aliases or self._analyzer._match_confidence(name, aliases) is not None:
            return True
        # Vendor-Ordner wie „JetBrains“ oder „BraveSoftware“: zählt, wenn ein Unterordner bekannt ist.
        candidates = {name, name.casefold(), re.sub(r"[^a-z0-9.+-]", "", name.casefold())}
        return any(candidate and self._which(candidate) for candidate in candidates)


def _children(root: Path) -> list[Path]:
    try:
        return sorted(
            path for path in root.iterdir()
            if path.is_dir() and not path.is_symlink() and not path.name.startswith(".")
        )
    except OSError:
        return []


def _leftover(path: Path, reason: str) -> Leftover:
    try:
        modified = path.stat().st_mtime
    except OSError:
        modified = 0.0
    return Leftover(path, reason, path_size(path), modified)


def _installed_package_names() -> set[str]:
    for binary, arguments in (
        ("dpkg-query", ("-W", "-f=${binary:Package}\n")),
        ("rpm", ("-qa", "--qf", "%{NAME}\n")),
        ("pacman", ("-Qq",)),
    ):
        if not shutil.which(binary):
            continue
        result = run_command((_trusted_binary(binary), *arguments), timeout=20)
        if result.returncode == 0:
            return {line.split(":", 1)[0].strip() for line in result.stdout.splitlines() if line.strip()}
    return set()


def _flatpak_ids() -> set[str] | None:
    if not shutil.which("flatpak"):
        return None
    result = run_command(("flatpak", "list", "--app", "--columns=application"), timeout=10)
    return {line.strip() for line in result.stdout.splitlines() if line.strip()} if result.returncode == 0 else None


def _snap_names() -> set[str] | None:
    if not shutil.which("snap"):
        return None
    result = run_command(("snap", "list"), timeout=10)
    if result.returncode != 0:
        return None
    return {line.split()[0] for line in result.stdout.splitlines()[1:] if line.split()}

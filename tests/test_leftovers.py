from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from restlos.leftovers import LeftoverScanner
from restlos.models import AppRecord, SourceKind


class LeftoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        for relative in (
            ".config/OldGame", ".config/gimp", ".config/htop", ".config/gtk-3.0", ".config/JetBrains",
            ".cache/OldGame", ".var/app/org.removed.App", ".var/app/org.gimp.GIMP", "snap/oldsnap",
            "snap/firefox", ".local/share/gnome-shell",
        ):
            (self.home / relative).mkdir(parents=True)
        (self.home / ".cache/OldGame/blob.bin").write_bytes(b"x" * 4096)
        self.apps = [
            AppRecord("flatpak:user:org.gimp.GIMP", "GIMP", SourceKind.FLATPAK, "org.gimp.GIMP"),
            AppRecord("snap:firefox", "Firefox", SourceKind.SNAP, "firefox"),
        ]

    def scan(self, *, flatpaks: set[str] | None = None, snaps: set[str] | None = None) -> dict[str, str]:
        scanner = LeftoverScanner(
            self.home,
            installed_packages=lambda: {"htop"},
            which=lambda name: "/usr/bin/idea" if name.casefold() == "jetbrains" else None,
            flatpak_ids=lambda: flatpaks,
            snap_names=lambda: snaps,
        )
        return {str(item.path.relative_to(self.home)): item.reason for item in scanner.scan(self.apps)}

    def test_finds_only_data_of_removed_programs(self) -> None:
        found = self.scan(flatpaks={"org.gimp.GIMP"}, snaps={"firefox", "core22"})
        self.assertEqual(
            set(found),
            {".config/OldGame", ".cache/OldGame", ".var/app/org.removed.App", "snap/oldsnap"},
        )
        self.assertIn("Flatpak", found[".var/app/org.removed.App"])
        # Größte Funde zuerst.
        self.assertEqual(next(iter(found)), ".cache/OldGame")

    def test_unknown_flatpak_or_snap_state_reports_nothing_there(self) -> None:
        found = self.scan(flatpaks=None, snaps=None)
        self.assertNotIn(".var/app/org.removed.App", found)
        self.assertNotIn("snap/oldsnap", found)
        self.assertIn(".config/OldGame", found)


if __name__ == "__main__":
    unittest.main()

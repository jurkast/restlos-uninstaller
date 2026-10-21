"""Welche Prozesse beim Entfernen beendet werden – mit nachgebautem /proc."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from restlos.models import AppRecord, Confidence, RemovalAction, RemovalPlan, RemovalTarget, SourceKind
from restlos.remover import RelatedProcess, RemovalExecutor


class ProcessSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.game = self.home / ".local/share/Steam/steamapps/common/Celeste"
        self.game.mkdir(parents=True)
        (self.game / "Celeste.bin").write_bytes(b"x")
        self.other_game = self.home / ".local/share/Steam/steamapps/common/Hades"
        self.other_game.mkdir(parents=True)
        self.prefix = self.home / ".local/share/Steam/steamapps/compatdata/504230"
        self.prefix.mkdir(parents=True)
        self.binaries = self.root / "usr/bin"
        self.binaries.mkdir(parents=True)
        for name in ("steam", "lutris", "wineserver", "bash"):
            (self.binaries / name).write_bytes(b"")

    def process(self, pid: int, comm: str, exe: Path, *, cwd: Path | None = None, args: tuple[str, ...] = (),
                environ: dict[str, str] | None = None) -> None:
        entry = self.proc / str(pid)
        entry.mkdir()
        (entry / "exe").symlink_to(exe)
        (entry / "cwd").symlink_to(cwd or self.root)
        (entry / "comm").write_text(comm + "\n", encoding="utf-8")
        (entry / "cmdline").write_bytes(b"\0".join(part.encode() for part in (str(exe), *args)) + b"\0")
        (entry / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in (environ or {}).items()))

    def plan(self, source: SourceKind, targets: list[Path], *, library_action: bool = False) -> RemovalPlan:
        app = AppRecord(f"{source.name}:demo", "Demo", source, "demo")
        actions = [RemovalAction("Bibliothek", internal_kind="lutris-database")] if library_action else []
        return RemovalPlan(app, [RemovalTarget(path, "Test", 0, Confidence.CERTAIN) for path in targets], actions)

    def test_steam_client_and_other_games_keep_running(self) -> None:
        self.process(10, "steam", self.binaries / "steam", args=("-silent",))
        self.process(11, "Celeste.bin", self.game / "Celeste.bin", cwd=self.game)
        self.process(12, "Hades.exe", self.binaries / "bash", cwd=self.other_game, args=("steam", "AppId=1145360"))
        self.process(13, "wineserver", self.binaries / "wineserver", environ={"STEAM_COMPAT_DATA_PATH": str(self.prefix)})
        self.process(14, "reaper", self.binaries / "bash", args=("SteamLaunch", "--", str(self.game / "Celeste.bin")))
        found = RemovalExecutor(self.home).related_processes(self.plan(SourceKind.STEAM, [self.game, self.prefix]),
                                                             proc=self.proc)
        self.assertEqual(sorted(item.pid for item in found), [11, 13, 14])
        self.assertFalse(any(item.launcher for item in found))

    def test_launcher_only_when_its_library_is_changed(self) -> None:
        self.process(20, "lutris", self.binaries / "lutris")
        plain = RemovalExecutor(self.home).related_processes(self.plan(SourceKind.LUTRIS, [self.game]), proc=self.proc)
        self.assertEqual(plain, [])
        library = RemovalExecutor(self.home).related_processes(
            self.plan(SourceKind.LUTRIS, [self.game], library_action=True), proc=self.proc)
        self.assertEqual(library, [RelatedProcess(20, "lutris", True)])

    def test_launchers_are_never_killed_and_reported_when_still_running(self) -> None:
        signals: list[tuple[int, int]] = []
        with patch("restlos.remover.os.kill", side_effect=lambda pid, sig: signals.append((pid, sig))), \
                patch("restlos.remover.time.monotonic", side_effect=[0.0, 100.0]), \
                patch("restlos.remover.Path.exists", return_value=True):
            remaining = RemovalExecutor(self.home).stop_processes(
                [RelatedProcess(30, "lutris", True), RelatedProcess(31, "game")])
        self.assertEqual(remaining, [RelatedProcess(30, "lutris", True)])
        self.assertIn((30, 15), signals)
        self.assertNotIn((30, 9), signals)
        self.assertIn((31, 9), signals)


if __name__ == "__main__":
    unittest.main()

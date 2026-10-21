#!/usr/bin/env python3
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _run_prepared_version(target: Path) -> int | None:
    """Vorbereitete Version starten und überwachen.

    Beendet sie sich, bevor sie ihren erfolgreichen Start gemeldet hat (Absturz beim Import,
    fehlende Bibliothek …), schaltet die installierte Version sofort zurück und startet selbst –
    die Nutzerin oder der Nutzer sieht also immer ein Fenster. Gibt None zurück, wenn die
    installierte Version übernehmen soll, sonst den Exit-Code der neuen Version.
    """
    from restlos.updater import Updater

    child = subprocess.Popen([sys.executable, "-I", "-B", str(target / "run_restlos.py"), *sys.argv[1:]])

    def forward(signum: int, _frame: object) -> None:
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, forward)
    code = child.wait()
    try:
        # Fehlercode = Absturz; ein Signal (Abmelden, Strg+C) ist kein Fehler der neuen Version.
        if Updater(root=ROOT, base=ROOT).abandon_failed_launch(target.name, crashed=code > 0):
            return None
    except Exception:  # Rückfallprüfung darf nie den Start der installierten Version verhindern.
        return None
    return code


# Die installierte Basisversion entscheidet, ob eine signiert geprüfte, vorbereitete Version
# startet. Eine gestartete Update-Version wählt nicht erneut (sonst Endlosschleife).
if os.environ.get("RESTLOS_LAUNCH_CHOSEN") != "1":
    os.environ["RESTLOS_BASE_DIR"] = str(ROOT)
    os.environ["RESTLOS_LAUNCH_CHOSEN"] = "1"
    try:
        from restlos.updater import Updater  # noqa: E402

        target = Updater(root=ROOT, base=ROOT).choose_launch()
    except Exception:  # Startfähigkeit der installierten Version hat Vorrang.
        target = ROOT
    if target != ROOT:
        result = _run_prepared_version(target)
        if result is not None:
            raise SystemExit(result)

from restlos.cli import main  # noqa: E402

raise SystemExit(main())

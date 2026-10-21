#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

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
        script = target / "run_restlos.py"
        os.execv(sys.executable, [sys.executable, "-I", "-B", str(script), *sys.argv[1:]])

from restlos.cli import main  # noqa: E402

raise SystemExit(main())

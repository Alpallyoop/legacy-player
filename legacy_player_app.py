"""Entry point of the downloadable Legacy Player app (built with PyInstaller as a folder: LegacyPlayer.exe + _internal).

    LegacyPlayer.exe                    opens the app window
    LegacyPlayer.exe --games "D:\\Games"  also adds a games folder
    LegacyPlayer.exe --data-dir "D:\\LP"  keeps the files in that folder (default: LegacyPlayerData next to the exe)
    LegacyPlayer.exe --server-run ...   (internal) runs the multiplayer server
    LegacyPlayer.exe --social-run ...   (internal) runs the friends service (Friends > Run a friends service)
    LegacyPlayer.exe --relaunch-run ... (internal) waits for the app to close, then starts it again (after a move)
"""
from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path


def _data_dir_argument(argv: list[str]) -> Path | None:
    for i, arg in enumerate(argv):
        if arg == "--data-dir" and i + 1 < len(argv):
            return Path(argv[i + 1])
        if arg.startswith("--data-dir="):
            return Path(arg.split("=", 1)[1])
    return None


def _fix_stdio() -> None:
    """A windowed app has no console: send prints to app.log in the logs folder (<data folder>\\logs) instead of crashing.
    Nothing is written outside the Legacy Player folder (or the folder the player chose)."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    import os
    log = None
    try:
        from launcher import datadir
        where = datadir.resolve(_data_dir_argument(sys.argv))
        if where.folder is not None:
            log = datadir.open_app_log(where.folder)
    except Exception:
        log = None
    if log is None:                                   # no folder chosen yet: the launcher opens the log once there is one
        log = open(os.devnull, "w", encoding="utf-8")
        sys._lp_log_pending = True
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


def _relaunch() -> int:
    """LegacyPlayer.exe --relaunch-run <pid> <folder> <command...>: the Windows app's own way to start itself again once
    it has closed (the same helper the source version runs with python -c)."""
    from launcher.selfupdate import RELAUNCH_PY
    i = sys.argv.index("--relaunch-run")
    sys.argv = ["relaunch", *sys.argv[i + 1:]]
    exec(compile(RELAUNCH_PY, "relaunch", "exec"), {"__name__": "__relaunch__"})
    return 0


def main() -> int:
    multiprocessing.freeze_support()
    if "--relaunch-run" in sys.argv:                  # a tiny helper: it opens no log of its own
        return _relaunch()
    _fix_stdio()
    if "--server-run" in sys.argv:
        sys.argv.remove("--server-run")
        from server.api import json_server
        json_server.main()
        return 0
    if "--social-run" in sys.argv:
        sys.argv.remove("--social-run")
        from server.social.__main__ import main as social_main
        social_main()
        return 0
    from launcher.__main__ import main as launcher_main
    return launcher_main()


if __name__ == "__main__":
    raise SystemExit(main())

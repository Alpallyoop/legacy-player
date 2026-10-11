from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from . import datadir
from .app import LauncherApp
from .catalog import CatalogError
from .shell import make_opener
from .web import CLEANUP_LIMIT_SECONDS, acquire_instance_lock, arm_exit_watchdog, serve, wake_existing

DEFAULT_PORT = 8780
LOCK_WAIT_SECONDS = 20.0        # a closing Legacy Player (for example one restarting into an update) may take this long


def claim_data_folder(data_dir: Path, show: bool, wait: float = LOCK_WAIT_SECONDS):
    """One Legacy Player per data folder. Returns (lock, exit_code): the held lock and None, or None and the exit code
    after waking the one that is already running (0) or failing to reach it (1). A Legacy Player that is just closing is
    waited for, so this launch then starts normally."""
    lock = acquire_instance_lock(data_dir)
    if lock is not None:
        try:
            (Path(data_dir) / "instance.json").unlink()          # nobody else runs here: a leftover from a crash
        except OSError:
            pass
        return lock, None
    end = time.time() + wait
    while True:
        if wake_existing(data_dir, show=show):
            print("Legacy Player is already running" + ("; showing its window." if show else "."), flush=True)
            return None, 0
        lock = acquire_instance_lock(data_dir)
        if lock is not None:
            return lock, None
        if time.time() >= end:
            print("Legacy Player is already running for this data folder but does not answer. Close it (or end "
                  "LegacyPlayer in Task Manager) and try again.", file=sys.stderr, flush=True)
            return None, 1
        time.sleep(0.5)


def choose_data_folder(argument: Path | None, interactive: bool, picker=None) -> datadir.Resolution | None:
    """Which folder holds Legacy Player's files (see launcher/datadir.py). When the program's own folder can not be
    written to and nothing was chosen yet, the player picks one now. None when there is no folder to use."""
    where = datadir.resolve(argument)
    if where.folder is not None:
        return where
    text = (f"Legacy Player can not keep its files in its own folder ({where.program}), for example because it is under "
            "Program Files. Choose a folder for its files (your settings, emulators and saves).")
    picked = None
    if interactive:
        datadir.message_box(text)
        got = (picker or datadir.pick)("folder", "Choose where Legacy Player keeps its files")
        picked = got.get("path") or None
    if picked and datadir._in_use(Path(picked)) and not datadir.looks_like_data(Path(picked)):
        picked = str(Path(picked) / datadir.EXE_DATA_NAME)     # never mixed with the player's own files
    if not picked:
        datadir.message_box("No folder was chosen, so Legacy Player did not start. Move the Legacy Player folder somewhere "
                            "of your own (for example D:\\Legacy Player), or start it with --data-dir \"D:\\Some Folder\".")
        return None
    try:
        datadir.write_pointer(Path(picked), where.program)
    except OSError:
        datadir.message_box(f"Legacy Player uses {picked} this time, but can not remember it (it can not write in "
                            f"{where.program}). Start it with --data-dir \"{picked}\" or move the Legacy Player folder.")
    return datadir.Resolution(Path(picked), "picked", where.program, where.default)


def prepare_data_folder(data_dir: Path) -> None:
    """Before the app starts: temporary files go to <data folder>\\tmp, every log is in the logs folder, and an old folder
    left by a move is removed. Never raises."""
    for step in (lambda: datadir.setup_tempdir(data_dir), lambda: datadir.tidy_logs(data_dir)):
        try:
            step()
        except Exception as exc:            # a leftover that can not be tidied must never stop the app
            print(f"Could not tidy the data folder: {exc}", file=sys.stderr, flush=True)
    # removing a big old folder (downloaded emulators) can take a while: never keep the window waiting for it. If the app
    # closes first, the marker stays and the next start finishes the job.
    threading.Thread(target=datadir.finish_pending_move, args=(data_dir,), daemon=True, name="old-folder-removal").start()
    if getattr(sys, "_lp_log_pending", False):     # the windowed app had nowhere to log before the folder was chosen
        try:
            log = datadir.open_app_log(data_dir)
            sys.stdout = sys.stderr = log
            sys._lp_log_pending = False
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m launcher", description="Legacy Player library and launcher")
    parser.add_argument("--games", action="append", default=[], metavar="FOLDER",
                        help='a folder that holds your games, e.g. --games "D:\\Games" (repeatable; optional)')
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="where Legacy Player keeps its files (default: the LegacyPlayerData folder next to the program, "
                             "or the folder named in data-location.txt there; source: the checkout's data folder)")
    parser.add_argument("--port", type=int, default=None,
                        help=f"the port of the local page (default {DEFAULT_PORT}, or a free one when that is taken)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--window", action="store_true", default=getattr(sys, "frozen", False),
                        help="open in an app-style window and quit when it is closed (default in the downloadable app)")
    args = parser.parse_args()
    where = choose_data_folder(args.data_dir, interactive=not args.no_browser)
    if where is None:
        return 2
    args.data_dir = where.folder
    lock, code = claim_data_folder(args.data_dir, show=not args.no_browser)
    if lock is None:
        if args.games and code == 0:
            print("Add the games folder in the open app (Library folders); it was not added from here.", flush=True)
        return code if code is not None else 1
    prepare_data_folder(args.data_dir)
    app = LauncherApp(args.data_dir)
    app.data_location = where
    app.resume_after_restart()
    if args.games:
        missing = [g for g in args.games if not Path(g).is_dir()]
        if missing:
            print(f"Cannot find this games folder: {missing[0]}\n"
                  "Use the real path to your games folder (the docs show a placeholder). "
                  "You can also start without --games and add the folder in the app.", file=sys.stderr)
            return 2
        merged = list(dict.fromkeys(app.catalog.data["roots"] + [str(Path(g)) for g in args.games]))
        try:
            app.catalog.set_roots(merged)
        except CatalogError as exc:
            print(f"Could not use that folder: {exc}", file=sys.stderr)
            return 2
        app.rescan()
    serve(app, args.port or DEFAULT_PORT, open_browser=not args.no_browser,
          opener=make_opener(args.data_dir) if args.window and not args.no_browser else None,
          exit_when_closed=args.window, port_fallback=args.port is None)
    if args.window or app.quit_requested:
        # the app was closed on purpose: whatever thread is still busy, the process must end (it holds the port, the
        # data folder's lock, and for the exe the file an update has to replace)
        arm_exit_watchdog(CLEANUP_LIMIT_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

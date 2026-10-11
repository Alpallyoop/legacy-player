"""Where Legacy Player keeps its files: one folder, inside the Legacy Player folder itself or one the player picks.

Nothing goes to the user's profile folders (no ~/.legacy-player, no %LOCALAPPDATA%\\LegacyPlayer, no %TEMP%).

Which data folder is used (first match wins):
  1. --data-dir FOLDER on the command line
  2. data-location.txt next to the program (the exe's folder; the checkout for `python -m launcher`): one line, the folder
  3. <program folder>\\LegacyPlayerData (the Windows app) or <checkout>\\data (source; ignored by git), when it is already
     in use
  4. ~/.legacy-player, the old place, when it still holds files: used for now, and the app asks once whether to move
     them into the Legacy Player folder, to a folder the player picks, or keep them where they are
  5. the folder from 3, when the program folder can be written to
  6. otherwise (for example under Program Files) the player is asked to pick a folder

Inside the data folder:
  logs\\                app.log, server.log, service.log, launcher.log, apply.log and reports\\ (the player can choose
                       another folder for logs: logs-location.txt)
  tmp\\                 temporary files (Python's tempfile and the TEMP of programs Legacy Player starts); emptied at start
  window_profile\\, overlay_profile\\   the app window's own browser profile

Moving (the in-app Change button, or the one-time question): the files are copied, the copy is checked, saved paths that
pointed inside the old folder are rewritten, and the old folder is removed by the next start, once nothing runs from it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

POINTER_NAME = "data-location.txt"
LOGS_POINTER_NAME = "logs-location.txt"
EXE_DATA_NAME = "LegacyPlayerData"
SOURCE_DATA_NAME = "data"
LEGACY_NAME = ".legacy-player"
MOVED_MARKER = "moved-from.json"            # in the new data folder: the old folder to remove at the next start
LOGS_MOVED_MARKER = "logs-moved-from.txt"   # in the data folder: the old logs folder to empty at the next start
LOG_NAMES = ("app.log", "server.log", "service.log", "launcher.log", "apply.log")
# never copied when the data folder moves: locks and state of the running app, temporary files, and the browser profiles
# the open window holds (they are made again)
COPY_SKIP = frozenset({"instance.lock", "instance.json", "tmp", "window_profile", "overlay_profile", MOVED_MARKER})
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def program_folder() -> Path:
    """The Legacy Player folder: the folder of LegacyPlayer.exe, or the git checkout when run from source."""
    if frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def default_folder(program: Path | None = None, is_frozen: bool | None = None) -> Path:
    program = program_folder() if program is None else Path(program)
    is_frozen = frozen() if is_frozen is None else is_frozen
    return program / (EXE_DATA_NAME if is_frozen else SOURCE_DATA_NAME)


def pointer_path(program: Path | None = None) -> Path:
    return (program_folder() if program is None else Path(program)) / POINTER_NAME


def legacy_folder(home: Path | None = None) -> Path:
    return (Path.home() if home is None else Path(home)) / LEGACY_NAME


def same(a: Path | str, b: Path | str) -> bool:
    try:
        return os.path.normcase(str(Path(a).resolve())) == os.path.normcase(str(Path(b).resolve()))
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


def inside(path: Path | str, folder: Path | str) -> bool:
    """Is `path` the folder itself or somewhere under it?"""
    try:
        p = os.path.normcase(str(Path(path).resolve()))
        f = os.path.normcase(str(Path(folder).resolve()))
    except OSError:
        return False
    return p == f or p.startswith(f.rstrip("\\/") + os.sep)


def _in_use(folder: Path) -> bool:
    try:
        return folder.is_dir() and any(folder.iterdir())
    except OSError:
        return False


def writable(folder: Path) -> bool:
    """Can this process create files in `folder` (or in the nearest folder above it that exists)?"""
    probe_dir = Path(folder)
    while not probe_dir.exists() and probe_dir.parent != probe_dir:
        probe_dir = probe_dir.parent
    probe = probe_dir / f".lp-write-test-{os.getpid()}"
    try:
        with open(probe, "wb") as f:
            f.write(b"ok")
        probe.unlink()
        return True
    except OSError:
        try:
            probe.unlink()
        except OSError:
            pass
        return False


def read_pointer(program: Path | None = None) -> Path | None:
    """The folder named in data-location.txt, or None. A relative path counts from the program folder."""
    program = program_folder() if program is None else Path(program)
    try:
        text = pointer_path(program).read_text(encoding="utf-8-sig").strip().strip('"')
    except (OSError, UnicodeDecodeError):
        return None
    line = text.splitlines()[0].strip().strip('"') if text else ""
    if not line:
        return None
    p = Path(os.path.expandvars(line))
    return p if p.is_absolute() else (program / p)


def write_pointer(target: Path | None, program: Path | None = None) -> None:
    """Remember the data folder next to the program (None: forget it, so the default is used). Raises OSError."""
    path = pointer_path(program)
    if target is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(str(Path(target)) + "\n", encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class Resolution:
    folder: Path | None             # None: the player has to pick one first (source == "choose")
    source: str                     # argument | pointer | default | legacy | choose
    program: Path = field(default_factory=program_folder)
    default: Path | None = None
    legacy: Path | None = None      # set when the old ~/.legacy-player is in use and the one-time question is due

    def as_dict(self) -> dict:
        return {"folder": str(self.folder) if self.folder else "", "source": self.source, "program": str(self.program),
                "default": str(self.default) if self.default else "", "legacy": str(self.legacy) if self.legacy else ""}


def resolve(argument: Path | str | None = None, *, program: Path | None = None, home: Path | None = None,
            is_frozen: bool | None = None) -> Resolution:
    program = program_folder() if program is None else Path(program)
    default = default_folder(program, is_frozen)
    if argument:
        return Resolution(Path(argument), "argument", program, default)
    pointed = read_pointer(program)
    if pointed is not None:
        return Resolution(pointed, "pointer", program, default)
    if _in_use(default):
        return Resolution(default, "default", program, default)
    old = legacy_folder(home)
    if _in_use(old):
        return Resolution(old, "legacy", program, default, legacy=old)
    if writable(program):
        return Resolution(default, "default", program, default)
    return Resolution(None, "choose", program, default)


# --- logs ---------------------------------------------------------------------------------------------------------
def logs_folder(data_dir: Path) -> Path:
    """Where every log goes: <data folder>\\logs, or the folder the player chose (logs-location.txt)."""
    data_dir = Path(data_dir)
    try:
        line = (data_dir / LOGS_POINTER_NAME).read_text(encoding="utf-8-sig").strip().strip('"')
    except (OSError, UnicodeDecodeError):
        line = ""
    if line:
        p = Path(line.splitlines()[0].strip())
        if p.is_absolute():
            return p
    return data_dir / "logs"


def logs_custom(data_dir: Path) -> bool:
    return not same(logs_folder(data_dir), Path(data_dir) / "logs")


def set_logs_folder(data_dir: Path, target: Path | str | None) -> Path:
    """Choose the logs folder (None or "": back to <data folder>\\logs). The files already there move at the next start,
    when nothing has them open. Returns the new folder. Raises ValueError / OSError."""
    data_dir = Path(data_dir)
    old = logs_folder(data_dir)
    new = Path(target) if target else data_dir / "logs"
    if not new.is_absolute():
        raise ValueError("Use a full folder path.")
    new.mkdir(parents=True, exist_ok=True)
    if not writable(new):
        raise ValueError("Legacy Player can not write in that folder. Pick another one.")
    pointer = data_dir / LOGS_POINTER_NAME
    if same(new, data_dir / "logs"):
        try:
            pointer.unlink()
        except FileNotFoundError:
            pass
    else:
        pointer.write_text(str(new) + "\n", encoding="utf-8")
    if not same(old, new):
        (data_dir / LOGS_MOVED_MARKER).write_text(str(old) + "\n", encoding="utf-8")
    return new


def _append_or_move(src: Path, dst: Path) -> bool:
    """Move one log file. When the target already exists, the old file's lines are added to its end. True when done."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            try:
                os.replace(src, dst)
                return True
            except OSError:
                shutil.copy2(src, dst)
        else:
            with open(src, "rb") as a, open(dst, "ab") as b:
                shutil.copyfileobj(a, b)
        src.unlink()
        return True
    except OSError:
        return False


def _move_reports(src: Path, dst: Path) -> None:
    if not src.is_dir() or same(src, dst):
        return
    for f in sorted(src.rglob("*")):
        if f.is_file():
            target = dst / f.relative_to(src)
            if not target.exists():
                _append_or_move(f, target)
    for d in sorted((p for p in src.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    try:
        src.rmdir()
    except OSError:
        pass


def old_app_log_folder() -> Path | None:
    """Where older versions of the Windows app wrote app.log (%LOCALAPPDATA%\\LegacyPlayer, not the install folder)."""
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "LegacyPlayer" if (base and sys.platform == "win32") else None


def tidy_logs(data_dir: Path, old_app_folder: Path | None = None) -> Path:
    """Bring every log into the logs folder: a move the player asked for, and the places older versions used
    (<data>\\launcher.log, <data>\\server\\server.log, <data>\\social\\service.log, <data>\\update\\apply.log,
    <data>\\reports, %LOCALAPPDATA%\\LegacyPlayer\\app.log). Files still held by a running program stay for the next
    start. Returns the logs folder. Never raises."""
    data_dir = Path(data_dir)
    logs = logs_folder(data_dir)
    try:
        logs.mkdir(parents=True, exist_ok=True)
    except OSError:
        return logs
    marker = data_dir / LOGS_MOVED_MARKER
    try:
        moved_from = Path(marker.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        moved_from = None
    if moved_from is not None:
        done = True
        if moved_from.is_absolute() and moved_from.is_dir() and not same(moved_from, logs):
            for name in LOG_NAMES:
                f = moved_from / name
                if f.is_file() and not _append_or_move(f, logs / name):
                    done = False
            _move_reports(moved_from / "reports", logs / "reports")
            try:
                moved_from.rmdir()                     # only when nothing else is in it
            except OSError:
                pass
        if done:
            try:
                marker.unlink()
            except OSError:
                pass
    for src in (data_dir / "launcher.log", data_dir / "server" / "server.log", data_dir / "social" / "service.log",
                data_dir / "update" / "apply.log"):
        if src.is_file() and not same(src.parent, logs):
            _append_or_move(src, logs / src.name)
    _move_reports(data_dir / "reports", logs / "reports")
    old = old_app_log_folder() if old_app_folder is None else old_app_folder
    if old is not None and old.is_dir() and not same(old, logs) and not inside(logs, old):
        try:
            names = {p.name for p in old.iterdir()}
        except OSError:
            names = set()
        if names and names <= {"app.log"}:            # only ever the folder older versions made for that one file
            _append_or_move(old / "app.log", logs / "app.log")
        try:
            old.rmdir()
        except OSError:
            pass
    return logs


def open_app_log(data_dir: Path):
    """The log file the windowed app prints to. Never raises: falls back to a sink that drops everything."""
    try:
        folder = logs_folder(data_dir)
        folder.mkdir(parents=True, exist_ok=True)
        return open(folder / "app.log", "a", buffering=1, encoding="utf-8")
    except OSError:
        return open(os.devnull, "w", encoding="utf-8")


# --- temporary files ----------------------------------------------------------------------------------------------
def setup_tempdir(data_dir: Path, set_env: bool = True) -> Path:
    """<data folder>\\tmp becomes the temporary folder of this process (tempfile) and of the programs it starts (TEMP,
    TMP). Whatever an earlier run left there is removed first (files still in use stay)."""
    tmp = Path(data_dir) / "tmp"
    if tmp.is_dir():
        for child in list(tmp.iterdir()):
            try:
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
            except OSError:
                pass
    tmp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(tmp)
    if set_env:
        for key in ("TEMP", "TMP", "TMPDIR"):
            if key != "TMPDIR" or sys.platform != "win32":
                os.environ[key] = str(tmp)
    return tmp


# --- moving the data folder ---------------------------------------------------------------------------------------
class MoveError(ValueError):
    """Why the files were not moved; safe to show the player."""


def looks_like_data(folder: Path) -> bool:
    folder = Path(folder)
    return (folder / "user_data.json").is_file() or any((folder / n).is_dir() for n in ("emulators", "server", "covers", "saves"))


def choose_target(source: Path, picked: Path) -> Path:
    """The folder the files go to. A picked folder that already holds other things gets a LegacyPlayerData folder
    inside it, so Legacy Player never mixes its files with the player's. Raises MoveError."""
    source, picked = Path(source), Path(picked)
    if not picked.is_absolute():
        raise MoveError("Use a full folder path, for example D:\\Legacy Player.")
    if same(source, picked):
        raise MoveError("Legacy Player already keeps its files there.")
    target = picked
    if _in_use(picked):
        if looks_like_data(picked):
            raise MoveError("That folder already holds Legacy Player files. Pick an empty folder, or start Legacy Player "
                            "with that folder instead.")
        target = picked / EXE_DATA_NAME
        if _in_use(target):
            raise MoveError(f"{target} is not empty. Pick an empty folder.")
    if inside(target, source):
        raise MoveError("The new folder can not be inside the folder Legacy Player uses now.")
    if inside(source, target):
        raise MoveError("The new folder can not contain the folder Legacy Player uses now.")
    return target


def _walk(folder: Path, skip=COPY_SKIP):
    """(relative path, size) of every file to copy, skipping the top-level names in `skip`."""
    folder = Path(folder)
    for root, dirs, files in os.walk(folder):
        rel_root = Path(root).relative_to(folder)
        if rel_root == Path("."):
            dirs[:] = [d for d in dirs if d not in skip]
            files = [f for f in files if f not in skip]
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for name in files:
            p = Path(root) / name
            if p.is_symlink():
                continue
            try:
                yield rel_root / name, p.stat().st_size
            except OSError:
                continue


def folder_size(folder: Path) -> tuple[int, int]:
    files = total = 0
    for _rel, size in _walk(folder):
        files += 1
        total += size
    return files, total


def copy_tree(source: Path, target: Path, progress=None) -> dict:
    """Copy the data folder (without COPY_SKIP). `progress(done_bytes, total_bytes)`. Raises OSError."""
    items = list(_walk(source))
    total = sum(s for _r, s in items)
    done = 0
    target.mkdir(parents=True, exist_ok=True)
    for rel, size in items:
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, dst)
        done += size
        if progress:
            progress(done, total)
    # empty folders too (an emulator may expect them)
    for root, dirs, _files in os.walk(source):
        rel_root = Path(root).relative_to(source)
        if rel_root == Path("."):
            dirs[:] = [d for d in dirs if d not in COPY_SKIP]
        for d in dirs:
            (target / rel_root / d).mkdir(parents=True, exist_ok=True)
    return {"files": len(items), "bytes": total}


def verify_copy(source: Path, target: Path) -> list[str]:
    """Files that are missing or differ in size in the copy. A log file that grew while copying is fine."""
    problems = []
    for rel, size in _walk(source):
        dst = target / rel
        try:
            got = dst.stat().st_size
        except OSError:
            problems.append(f"{rel} is missing")
            continue
        if got != size and not (rel.suffix.lower() == ".log" and got <= size):
            problems.append(f"{rel} differs ({got} of {size} bytes)")
    return problems


def rewrite_value(value, old: str, new: str):
    """`value` with every path string inside `old` pointed at the same place inside `new` (dicts and lists too)."""
    if isinstance(value, dict):
        return {k: rewrite_value(v, old, new) for k, v in value.items()}
    if isinstance(value, list):
        return [rewrite_value(v, old, new) for v in value]
    if isinstance(value, str) and value:
        a, b = os.path.normcase(value), os.path.normcase(old.rstrip("\\/"))
        if a == b:
            return new
        if a[:len(b) + 1] in (b + "\\", b + "/"):
            parts = [p for p in value[len(b) + 1:].replace("\\", "/").split("/") if p]
            return str(Path(new).joinpath(*parts))
    return value


def rewrite_saved_paths(target: Path, old: Path, new: Path) -> int:
    """Saved paths in the copied settings (emulator programs Legacy Player installed, save and backup folders, ...) that
    pointed inside the old folder now point inside the new one. Returns how many files changed."""
    changed = 0
    for name in ("user_data.json", "library_cache.json"):
        path = Path(target) / name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        fixed = rewrite_value(data, str(old), str(new))
        if fixed != data:
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(fixed, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(tmp, path)
            changed += 1
    return changed


def programs_running_inside(folder: Path, exclude=(), lister=None) -> list[str]:
    """Programs (full paths) running from inside `folder`, for example an emulator Legacy Player installed there."""
    folder = Path(folder)
    skip = {os.getpid(), *exclude}
    out = []
    for pid, exe in (lister or _running_programs)():
        if pid in skip or not exe:
            continue
        if inside(exe, folder):
            out.append(exe)
    return sorted(set(out))


def _running_programs() -> list[tuple[int, str]]:
    try:
        import psutil                                    # bundled in the Windows app
        found = []
        for p in psutil.process_iter(["pid", "exe"]):
            try:
                found.append((p.info["pid"], p.info.get("exe") or ""))
            except Exception:
                continue
        return found
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "Get-CimInstance Win32_Process | ForEach-Object { \"$($_.ProcessId)`t$($_.ExecutablePath)\" }"],
                                 capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW)
            rows = []
            for line in out.stdout.splitlines():
                pid, _, exe = line.partition("\t")
                if pid.strip().isdigit():
                    rows.append((int(pid), exe.strip()))
            return rows
        except (OSError, subprocess.SubprocessError):
            return []
    rows = []
    for d in Path("/proc").glob("[0-9]*"):
        try:
            rows.append((int(d.name), os.readlink(d / "exe")))
        except OSError:
            continue
    return rows


def move_data(source: Path, target: Path, *, program: Path | None = None, default: Path | None = None, progress=None,
              lister=None) -> dict:
    """Copy the data folder to `target`, check the copy, fix saved paths, and make `target` the data folder. The old
    folder stays until the next start (it is in use now) and is removed then. Raises MoveError; leaves no half copy."""
    source, target = Path(source), Path(target)
    program = program_folder() if program is None else Path(program)
    running = programs_running_inside(source, lister=lister)
    if running:
        names = ", ".join(Path(r).name for r in running[:4])
        raise MoveError(f"Close {names} first: it runs from the folder that is being moved.")
    files, total = folder_size(source)
    made = not target.exists()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MoveError(f"Could not create {target}: {exc.strerror or exc}") from exc
    if not writable(target):
        if made:
            shutil.rmtree(target, ignore_errors=True)
        raise MoveError("Legacy Player can not write in that folder. Pick another one.")
    try:
        free = shutil.disk_usage(target).free
    except OSError:
        free = None
    if free is not None and free < total + 50 * 1024 * 1024:
        if made:
            shutil.rmtree(target, ignore_errors=True)
        raise MoveError(f"Not enough free space there: the files need {round(total / 1048576)} MB.")
    is_default = same(target, default if default is not None else default_folder(program))
    if not is_default and not writable(program):
        if made:
            shutil.rmtree(target, ignore_errors=True)
        raise MoveError(f"Legacy Player can not remember a new place, because it can not write in its own folder ({program}). "
                        "Move the Legacy Player folder somewhere of your own first.")

    def undo():
        if made:
            shutil.rmtree(target, ignore_errors=True)
        else:
            for rel, _s in _walk(source):
                try:
                    (target / rel).unlink()
                except OSError:
                    pass
    try:
        copied = copy_tree(source, target, progress)
    except OSError as exc:
        undo()
        raise MoveError(f"Copying stopped: {exc.strerror or exc}. Nothing was changed; your files are still in {source}.") from exc
    problems = verify_copy(source, target)
    if problems:
        undo()
        raise MoveError("The copy did not match (" + "; ".join(problems[:3]) + f"). Nothing was changed; your files are still in {source}.")
    try:
        rewrite_saved_paths(target, source, target)
        (target / MOVED_MARKER).write_text(json.dumps({"from": str(source), "at": time.time(), "files": files}), encoding="utf-8")
        write_pointer(None if is_default else target, program)
    except OSError as exc:
        undo()
        raise MoveError(f"Could not finish the move: {exc.strerror or exc}. Nothing was changed.") from exc
    return {"from": str(source), "to": str(target), "files": copied["files"], "bytes": copied["bytes"]}


def finish_pending_move(data_dir: Path, lister=None) -> dict | None:
    """At start: remove the old folder a move left behind, once nothing runs from it. Returns what happened, or None
    when there was nothing to do. Never raises."""
    data_dir = Path(data_dir)
    marker = data_dir / MOVED_MARKER
    try:
        info = json.loads(marker.read_text(encoding="utf-8"))
        old = Path(info["from"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    out = {"from": str(old), "removed": False, "message": ""}
    if not old.exists():
        out["removed"] = True
    elif same(old, data_dir) or inside(old, data_dir) or inside(data_dir, old) or not old.is_absolute():
        out["message"] = "The old folder was not removed, because it overlaps the new one."
    elif _in_use(old) and not looks_like_data(old):
        out["message"] = f"{old} was left alone: it does not look like Legacy Player's folder."
    else:
        running = programs_running_inside(old, lister=lister)
        if running:
            out["message"] = f"The old folder {old} is removed once {Path(running[0]).name} is closed (next start)."
            return out
        problems = []

        def onerror(func, p, exc):
            try:
                os.chmod(p, 0o700)
                func(p)
            except OSError:
                problems.append(p)
        shutil.rmtree(old, onerror=onerror)
        if problems or old.exists():
            out["message"] = f"Some files in the old folder {old} are still in use; Legacy Player tries again at the next start."
            return out
        out["removed"] = True
    try:
        marker.unlink()
    except OSError:
        pass
    return out


# --- the Windows folder / file pickers ----------------------------------------------------------------------------
_PICK_PS1 = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true; $owner.ShowInTaskbar = $false; $owner.Opacity = 0
$owner.StartPosition = 'CenterScreen'; $owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.Show(); $owner.Activate()
$title = $env:LP_PICK_TITLE; $initial = $env:LP_PICK_INITIAL
if ($env:LP_PICK_KIND -eq 'file') {
    $d = New-Object System.Windows.Forms.OpenFileDialog
    $d.Title = $title
    $d.Filter = $env:LP_PICK_FILTER
    $d.CheckFileExists = $true; $d.Multiselect = $false
    if ($initial) {
        if (Test-Path -LiteralPath $initial -PathType Leaf) { $d.InitialDirectory = [System.IO.Path]::GetDirectoryName($initial); $d.FileName = [System.IO.Path]::GetFileName($initial) }
        elseif (Test-Path -LiteralPath $initial -PathType Container) { $d.InitialDirectory = $initial }
    }
    $r = $d.ShowDialog($owner); $picked = $d.FileName
} else {
    $d = New-Object System.Windows.Forms.FolderBrowserDialog
    $d.Description = $title; $d.ShowNewFolderButton = $true
    if ($initial -and (Test-Path -LiteralPath $initial -PathType Container)) { $d.SelectedPath = $initial }
    $r = $d.ShowDialog($owner); $picked = $d.SelectedPath
}
$owner.Close()
if ($r -eq [System.Windows.Forms.DialogResult]::OK -and $picked) { [Console]::Out.Write("PICKED:" + $picked); exit 0 }
exit 1
"""

_pick_lock = threading.Lock()


def _pick_windows(kind: str, title: str, initial: str, exe_only: bool, runner) -> dict:
    env = dict(os.environ)
    env.update({"LP_PICK_KIND": kind, "LP_PICK_TITLE": title, "LP_PICK_INITIAL": initial or "",
                "LP_PICK_FILTER": "Programs (*.exe)|*.exe|All files (*.*)|*.*" if exe_only else "All files (*.*)|*.*"})
    try:
        from .childenv import clean_env
        env = clean_env(env)
    except ImportError:
        pass
    done = runner(["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                   "-Command", _PICK_PS1], capture_output=True, timeout=1800, env=env, creationflags=_NO_WINDOW)
    text = done.stdout.decode("utf-8", "replace") if isinstance(done.stdout, bytes) else (done.stdout or "")
    if done.returncode == 0 and "PICKED:" in text:
        return {"available": True, "cancelled": False, "path": text.split("PICKED:", 1)[1].strip()}
    if done.returncode == 1:
        return {"available": True, "cancelled": True, "path": ""}
    err = done.stderr.decode("utf-8", "replace") if isinstance(done.stderr, bytes) else (done.stderr or "")
    raise OSError(err.strip().splitlines()[-1] if err.strip() else f"the picker ended with code {done.returncode}")


def _pick_tk(kind: str, title: str, initial: str, exe_only: bool) -> dict:
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk()
    try:
        root.withdraw()
        root.attributes("-topmost", True)
        if kind == "file":
            start = initial and (Path(initial).parent if Path(initial).is_file() else Path(initial))
            types = [("Programs", "*.exe"), ("All files", "*")] if exe_only else [("All files", "*")]
            picked = filedialog.askopenfilename(parent=root, title=title, initialdir=str(start) if start else None, filetypes=types)
        else:
            picked = filedialog.askdirectory(parent=root, title=title, initialdir=initial or None, mustexist=False)
    finally:
        root.destroy()
    return {"available": True, "cancelled": not picked, "path": str(Path(picked)) if picked else ""}


def pick(kind: str = "folder", title: str = "", initial: str = "", exe_only: bool = False, runner=None,
         platform: str | None = None) -> dict:
    """Show the real Windows folder (or file) picker and return {available, cancelled, path, busy?, error?}. One picker
    at a time; the call waits until the player closes it (callers must not hold the app's lock)."""
    kind = "file" if kind == "file" else "folder"
    title = str(title or ("Choose a program" if kind == "file" else "Choose a folder"))[:200]
    initial = str(initial or "")[:1000]
    if not _pick_lock.acquire(blocking=False):
        return {"available": True, "cancelled": True, "path": "", "busy": True,
                "error": "A folder window is already open. Look for it behind the app."}
    try:
        if (platform or sys.platform) == "win32":
            try:
                return _pick_windows(kind, title, initial, exe_only, runner or subprocess.run)
            except (OSError, subprocess.SubprocessError) as exc:
                first = str(exc)
        else:
            first = ""
        try:
            return _pick_tk(kind, title, initial, exe_only)
        except Exception as exc:                           # no display, no tkinter: say so; the page offers typing a path
            return {"available": False, "cancelled": True, "path": "",
                    "error": f"Could not open a folder window here ({first or exc}). Type the path instead."}
    finally:
        _pick_lock.release()


def message_box(text: str, title: str = "Legacy Player") -> None:
    """A plain Windows message (the windowed app has no console). Elsewhere it prints. Never raises."""
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(text), str(title), 0x00000040 | 0x00010000)   # information, topmost
            return
    except Exception:
        pass
    try:
        print(text, file=sys.stderr, flush=True)
    except Exception:
        pass

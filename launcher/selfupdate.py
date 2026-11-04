"""Legacy Player updating itself, then restarting on the new version.

Two ways Legacy Player runs, two ways to update:
  * the Windows app (LegacyPlayer.exe): the newest GitHub release's zip is downloaded, checked against its published
    SHA-256, unpacked aside (in <data folder>/update) and checked again; then a small helper waits for this app to close,
    copies the new program (LegacyPlayer.exe and its _internal folder) over the folder the app runs from, and starts the
    new LegacyPlayer.exe. The data folder (LegacyPlayerData, or the one the player chose) is never touched.
  * a git checkout (`lp source`, `python -m launcher`): `git pull --ff-only`, then the app starts itself again.
In both cases files that were already updated on disk (for example someone ran `git pull`) only need the restart.

Nothing here runs without the player pressing a button: checking needs "Allow internet downloads", and installing
needs a confirmation in the app.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .childenv import clean_env
from .installer import GITHUB_HOSTS, InstallError, _open, extract_zip_safe, latest_release
from .version import REPO, VERSION
from . import version as _version

# The packaged app is a few dozen MB; anything far larger is not a Legacy Player release and is refused while downloading.
MAX_UPDATE_BYTES = 1024 * 1024 * 1024

ROOT = Path(__file__).resolve().parent.parent          # the checkout (source) or the unpacked bundle (exe)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_DETACHED = 0x00000008 | 0x00000200                    # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


MANIFEST_NAME = "manifest.json"     # in <data>/update, next to (not inside) the staged folder "new"


def signed_message(tag: str, name: str, sha256_hex: str) -> bytes:
    """What an update signature covers: the release tag, the zip's name and its SHA-256, so a signed old release can't be
    offered as a newer one (tools/sign_release.py makes the signature)."""
    return f"legacy-player-update-v1\n{tag}\n{name}\n{sha256_hex.lower()}\n".encode("utf-8")


def signature_ok(keys, tag: str, name: str, sha256_hex: str, sig_text: str) -> bool:
    from . import ed25519
    words = sig_text.split()
    try:
        sig = bytes.fromhex(words[0]) if words else b""
    except ValueError:
        return False
    msg = signed_message(tag, name, sha256_hex)
    for k in keys:
        try:
            if ed25519.verify(bytes.fromhex(k), msg, sig):
                return True
        except ValueError:
            continue
    return False


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_stage_manifest(stage: Path, manifest: Path) -> str:
    """Record the SHA-256 of every staged file, so apply.ps1 can check the folder is still exactly what was verified
    (nothing changed, added or removed) before it copies anything. Returns the manifest's own SHA-256, which goes on the
    helper's command line so the manifest cannot be swapped either."""
    files = []
    for p in sorted(Path(stage).rglob("*")):
        if p.is_symlink():
            raise InstallError("The unpacked package contains a link, so nothing was installed.")
        if p.is_file():
            files.append({"path": p.relative_to(stage).as_posix(), "sha256": _sha256_file(p)})
    if not files:
        raise InstallError("The unpacked package is empty, so nothing was installed.")
    body = json.dumps({"version": 1, "files": files}, ensure_ascii=True, indent=1).encode("ascii")
    Path(manifest).write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def nums(text: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(text))[:3])


def mode() -> str:
    """'exe' for the Windows app, 'git' for a checkout with git available, '' when this copy cannot update itself."""
    if getattr(sys, "frozen", False):
        return "exe"
    if (ROOT / ".git").exists() and shutil.which("git"):
        return "git"
    return ""


def version_on_disk() -> str:
    """The version written in the files (differs from the running VERSION after a `git pull` the app has not restarted for)."""
    try:
        m = re.search(r'VERSION\s*=\s*"([^"]+)"', (ROOT / "launcher" / "version.py").read_text(encoding="utf-8"))
        return m.group(1) if m else VERSION
    except OSError:
        return VERSION


def _git(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=_NO_WINDOW)


INSTALLER_FOLDER_PARTS = ("Programs", "LegacyPlayer")   # %LOCALAPPDATA%\Programs\LegacyPlayer: where the installer puts the app


def installer_folder() -> Path | None:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base).joinpath(*INSTALLER_FOLDER_PARTS) if base else None


def folder_writable(folder: Path) -> bool:
    """Can this process create (and remove) a file in the folder? (Program Files cannot, without administrator rights.)"""
    probe = Path(folder) / f".lp-write-test-{os.getpid()}"
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


def strip_data_dir(argv: list[str]) -> list[str]:
    """The arguments without --data-dir (after a move the new place is remembered next to the program instead)."""
    out, skip = [], False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg == "--data-dir":
            skip = True
            continue
        if arg.startswith("--data-dir="):
            continue
        out.append(arg)
    return out


def relaunch_command(log: Path, argv: list[str] | None = None, pid: int | None = None) -> list[str]:
    """A command that waits for this process to end, then starts Legacy Player again with `argv` (default: the same
    arguments). The source version writes the new app's output to `log`; the Windows app logs by itself."""
    argv = list(sys.argv[1:] if argv is None else argv)
    pid_text = str(os.getpid() if pid is None else pid)
    if getattr(sys, "frozen", False):
        exe = str(Path(sys.executable).resolve())
        return [exe, "--relaunch-run", pid_text, str(Path(exe).parent), exe, *argv]
    Path(log).parent.mkdir(parents=True, exist_ok=True)
    return [sys.executable, "-c", RELAUNCH_PY, pid_text, str(ROOT), "--log", str(log), sys.executable, "-m", "launcher", *argv]


def start_detached(command: list[str], cwd: str) -> None:
    """Start a helper that outlives this process, without a console window and without the parent's PyInstaller state."""
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                    "cwd": cwd, "env": clean_env()}
    if sys.platform == "win32":
        kwargs["creationflags"] = _DETACHED | _NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


class SelfUpdate:
    """One update at a time. `state` is idle / checking / downloading / ready / restarting / problem."""

    def __init__(self, data_dir: Path, logs_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.logs_dir = Path(logs_dir) if logs_dir is not None else self.data_dir / "logs"
        self.lock = threading.Lock()
        self._work = threading.Lock()                     # one download or pull at a time (Update everything and the button)
        self.status: dict = {"state": "idle", "mode": mode(), "current": VERSION, "message": "", "latest": "", "done": 0, "total": 0}
        self.staged: dict | None = None
        self.mode = mode
        self.last_result: dict | None = self._read_result()

    def snapshot(self) -> dict:
        with self.lock:
            return dict(self.status)

    def _set(self, **kw) -> None:
        with self.lock:
            self.status.update(kw)

    # --- how the last update went (written by the helper that swapped the files) ---------------------------------
    def result_file(self) -> Path:
        return self.data_dir / "update" / "result.json"

    def _read_result(self) -> dict | None:
        """{'ok', 'tag', 'error', 'at'} from the last update, read once at start-up (the file is removed when delivered)."""
        try:
            raw = json.loads(self.result_file().read_text(encoding="utf-8-sig"))     # PowerShell writes UTF-8 with a BOM
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return {"ok": False, "tag": "", "error": "The last update left a result that could not be read.", "at": 0}
        if not isinstance(raw, dict):
            return None
        out = {"ok": bool(raw.get("ok")), "tag": str(raw.get("tag") or "")[:40], "error": str(raw.get("error") or "")[:400],
               "at": raw.get("at") or 0}
        if out["ok"] and out["tag"] and nums(out["tag"]) and nums(out["tag"]) != nums(VERSION):
            out["ok"] = False
            out["error"] = f"The new files were put in place, but this is still version {VERSION}."
        return out

    def take_last_result(self) -> dict | None:
        """The last update's result, once: after this it is forgotten (and its file removed)."""
        with self.lock:
            out, self.last_result = self.last_result, None
        if out is not None:
            try:
                self.result_file().unlink()
            except OSError:
                pass
        return out

    def _write_result(self, ok: bool, tag: str, error: str = "") -> None:
        try:
            self.result_file().parent.mkdir(parents=True, exist_ok=True)
            self.result_file().write_text(json.dumps({"ok": ok, "tag": tag, "error": error, "at": time.time()}), encoding="utf-8")
        except OSError:
            pass

    # --- what is newer --------------------------------------------------------------------------------------
    def check(self) -> dict:
        """{'newer': bool, 'latest': str, 'restart_only': bool, 'message': str, 'mode': ...}. Raises InstallError."""
        m = self.mode()
        if m == "git":
            disk = version_on_disk()
            fetched = _git("fetch", "--quiet", timeout=90)
            behind = 0
            if fetched.returncode == 0:
                count = _git("rev-list", "--count", "HEAD..@{u}")
                behind = int(count.stdout.strip() or 0) if count.returncode == 0 else 0
            if behind:
                return {"mode": m, "newer": True, "restart_only": False, "latest": f"{behind} new change{'s' if behind != 1 else ''}",
                        "message": f"Your copy is {behind} change{'s' if behind != 1 else ''} behind. Updating pulls them and restarts Legacy Player."}
            if nums(disk) != nums(VERSION):
                return {"mode": m, "newer": True, "restart_only": True, "latest": disk,
                        "message": f"Version {disk} is already in your folder; Legacy Player is still running {VERSION}. Restart to use it."}
            note = "" if fetched.returncode == 0 else " (could not reach the git server, so only your folder was checked)"
            return {"mode": m, "newer": False, "restart_only": False, "latest": VERSION, "message": f"You have the latest version ({VERSION}){note}."}
        rel = latest_release(REPO)
        newer = bool(nums(rel["tag"])) and nums(rel["tag"]) > nums(VERSION)
        return {"mode": m or "exe", "newer": newer, "restart_only": False, "latest": rel["tag"], "release": rel,
                "message": (f"Version {rel['tag']} is available (you have {VERSION})." if newer else f"You have the latest version ({VERSION}).")}

    # --- get it ready ---------------------------------------------------------------------------------------
    def prepare(self, info: dict | None = None) -> dict:
        """Download and check (exe) or pull (git). Leaves self.staged set so restart() can finish the job."""
        with self._work:
            return self._prepare(info)

    def _prepare(self, info: dict | None) -> dict:
        info = info or self.check()
        if not info.get("newer"):
            self._set(state="idle", message=info["message"])
            return self.snapshot()
        m = info["mode"]
        if m == "git":
            if not info.get("restart_only"):
                self._set(state="downloading", message="Pulling the new version…")
                out = _git("pull", "--ff-only", timeout=180)
                if out.returncode != 0:
                    why = (out.stderr or out.stdout or "").strip().splitlines()
                    msg = ("Your folder has changes of its own, so git would not update it. Commit or put them aside "
                           "(git stash), then try again." if any("local changes" in w or "diverged" in w or "Not possible to fast-forward" in w for w in why)
                           else "git could not update the folder: " + (why[-1] if why else "no reason given"))
                    self._set(state="problem", message=msg)
                    raise InstallError(msg)
            self.staged = {"mode": "git", "version": version_on_disk()}
            self._set(state="ready", latest=self.staged["version"], message=f"Version {self.staged['version']} is ready. Legacy Player restarts to use it.")
            return self.snapshot()
        if sys.platform != "win32":
            raise InstallError("The downloadable app is for Windows. On this system, update with git (lp source).")
        dest = Path(sys.executable).resolve().parent      # the copy that is running is the copy that gets updated
        exe = Path(sys.executable).resolve()
        if not folder_writable(dest):
            msg = (f"Legacy Player cannot change the folder it runs from ({dest}), for example because it is under Program Files. "
                   "Nothing was downloaded. Move the Legacy Player folder (LegacyPlayer.exe with its _internal folder) to a "
                   r"folder of your own (the installer uses %LOCALAPPDATA%\Programs\LegacyPlayer), or download the new "
                   "version from the releases page.")
            self._set(state="problem", message=msg)
            raise InstallError(msg)
        rel = info.get("release") or latest_release(REPO)
        zip_asset = next((a for a in rel["assets"] if re.fullmatch(r"LegacyPlayer-.*-win64\.zip", a["name"])), None)
        sum_asset = next((a for a in rel["assets"] if re.fullmatch(r"LegacyPlayer-.*-win64\.zip\.sha256", a["name"])), None)
        if not zip_asset or not sum_asset:
            raise InstallError(f"Release {rel['tag']} has no Windows package with a checksum, so nothing was installed.")
        sig_asset = next((a for a in rel["assets"] if a["name"] == zip_asset["name"] + ".sig"), None)
        if _version.UPDATE_SIGNING_KEYS and not sig_asset:
            msg = f"Release {rel['tag']} is not signed with the Legacy Player maintainers' key, so nothing was downloaded or installed."
            self._set(state="problem", message=msg)
            raise InstallError(msg)
        folder = self.data_dir / "update"
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        archive = folder / zip_asset["name"]
        self._set(state="downloading", latest=rel["tag"], message=f"Downloading {rel['tag']}…", done=0, total=zip_asset.get("size") or 0)
        with _open(sum_asset["url"], GITHUB_HOSTS, timeout=60) as response:
            words = response.read(4096).decode("utf-8", "replace").split()
        expected = words[0].lower() if words else ""
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            shutil.rmtree(folder, ignore_errors=True)
            msg = f"Release {rel['tag']} has an unreadable checksum file, so nothing was downloaded or installed."
            self._set(state="problem", message=msg)
            raise InstallError(msg)
        listed = int(zip_asset.get("size") or 0)
        digest = hashlib.sha256()
        with _open(zip_asset["url"], GITHUB_HOSTS, timeout=60) as response, open(archive, "wb") as out:
            done = 0
            while True:
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                done += len(chunk)
                if done > MAX_UPDATE_BYTES:
                    out.close()
                    shutil.rmtree(folder, ignore_errors=True)
                    msg = "The download exceeded its size limit and was stopped. Nothing was installed."
                    self._set(state="problem", message=msg)
                    raise InstallError(msg)
                out.write(chunk)
                digest.update(chunk)
                self._set(done=done)
        if (listed and done != listed) or digest.hexdigest().lower() != expected or (zip_asset.get("sha256") and zip_asset["sha256"].lower() != expected):
            shutil.rmtree(folder, ignore_errors=True)
            msg = "The download is damaged or was changed (checksum mismatch). Nothing was installed."
            self._set(state="problem", message=msg)
            raise InstallError(msg)
        if _version.UPDATE_SIGNING_KEYS:
            with _open(sig_asset["url"], GITHUB_HOSTS, timeout=60) as response:
                sig_text = response.read(1024).decode("ascii", "replace")
            if not signature_ok(_version.UPDATE_SIGNING_KEYS, rel["tag"], zip_asset["name"], expected, sig_text):
                shutil.rmtree(folder, ignore_errors=True)
                msg = (f"Release {rel['tag']} does not carry a valid signature from the Legacy Player maintainers, so it was "
                       "not installed. Download it from the releases page only if you trust it.")
                self._set(state="problem", message=msg)
                raise InstallError(msg)
        stage = folder / "new"
        extract_zip_safe(archive, stage)
        if not (stage / "LegacyPlayer.exe").exists():
            raise InstallError("The package has no LegacyPlayer.exe, so nothing was installed.")
        if getattr(sys, "frozen", False) and (Path(sys.executable).resolve().parent / "_internal").is_dir() \
                and not (stage / "_internal").is_dir():
            raise InstallError("The package has no _internal folder, so nothing was installed.")
        archive.unlink(missing_ok=True)
        # The package is trusted for its SHA-256 (from the same release) and, once UPDATE_SIGNING_KEYS lists a key, for
        # the maintainers' signature over tag, name and SHA-256. This manifest guards the staged files between that
        # check and the swap (audit 2026-11-04).
        manifest = folder / MANIFEST_NAME
        try:
            manifest_sha = write_stage_manifest(stage, manifest)
        except (OSError, InstallError) as exc:
            shutil.rmtree(folder, ignore_errors=True)
            msg = exc.args[0] if isinstance(exc, InstallError) else f"The unpacked update could not be recorded ({exc}). Nothing was installed."
            self._set(state="problem", message=msg)
            raise InstallError(msg) from exc
        self.staged = {"mode": "exe", "version": rel["tag"], "stage": str(stage), "dest": str(dest), "exe": str(exe),
                       "manifest": str(manifest), "manifest_sha256": manifest_sha}
        self._set(state="ready", message=f"Version {rel['tag']} is downloaded and checked. Legacy Player restarts to use it.")
        return self.snapshot()

    # --- swap and start again -------------------------------------------------------------------------------
    def restart_plan(self) -> list[str]:
        """The command that finishes the update after this process has exited, then starts the new version."""
        if not self.staged:
            raise InstallError("There is no update ready yet.")
        pid = str(os.getpid())
        if self.staged["mode"] == "exe":
            folder = Path(self.data_dir) / "update"
            folder.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            script = folder / "apply.ps1"
            script.write_text(APPLY_PS1, encoding="utf-8")
            exe = self.staged.get("exe") or str(Path(self.staged["dest"]) / "LegacyPlayer.exe")
            installed = installer_folder()
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script),
                    "-WaitPid", pid, "-Stage", self.staged["stage"], "-Dest", self.staged["dest"], "-Exe", exe,
                    "-Tag", self.staged["version"], "-Log", str(self.logs_dir / "apply.log"), "-Result", str(self.result_file()),
                    # without both, apply.ps1 refuses to copy anything
                    "-Manifest", self.staged.get("manifest") or str(folder / MANIFEST_NAME),
                    "-ManifestSha256", self.staged.get("manifest_sha256") or "",
                    *(["-Installed", str(installed)] if installed else [])]
        return relaunch_command(self.logs_dir / "launcher.log")

    def launch_helper(self) -> None:
        command = self.restart_plan()
        if self.staged["mode"] == "git":
            self._write_result(True, self.staged["version"])          # the restarted app says "Updated to …"
        # never the onefile temporary folder (ROOT in the exe) as working folder, and no onefile state for the new exe
        cwd = str(ROOT) if self.staged["mode"] == "git" else str(Path(self.data_dir) / "update")
        kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                        "cwd": cwd, "env": clean_env()}
        if sys.platform == "win32":
            kwargs["creationflags"] = _DETACHED | _NO_WINDOW
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(command, **kwargs)
        self._set(state="restarting", message=f"Restarting into {self.staged['version']}…")


# Waits for the old app to exit (and ends it if it is still there after 90 seconds: it asked to be replaced), then starts
# it again with the same arguments (git checkouts). Arguments: the old process, the folder to start in, optionally
# "--log <file>" (the new app's output goes there), then the command.
RELAUNCH_PY = r"""
import os, subprocess, sys, time
pid, root, cmd = int(sys.argv[1]), sys.argv[2], sys.argv[3:]
log = None
if cmd[:1] == ["--log"]:
    log, cmd = cmd[1], cmd[2:]
handle = None
if os.name == "nt":
    import ctypes
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = ctypes.c_void_p
    k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = k.OpenProcess(0x00100000 | 0x0001, False, pid)      # SYNCHRONIZE | PROCESS_TERMINATE: this very process
def alive():
    if os.name == "nt":
        return bool(handle) and k.WaitForSingleObject(handle, 0) == 0x102
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
end = time.time() + float(os.environ.get("LP_RELAUNCH_WAIT") or 90)
while alive() and time.time() < end:
    time.sleep(0.3)
if alive():                                    # it asked to be replaced, so it must not keep the port and the data folder
    try:
        if os.name == "nt":
            k.TerminateProcess(handle, 1)
            k.WaitForSingleObject(handle, 5000)
        else:
            import signal
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.5)
    except Exception:
        pass
if handle:
    k.CloseHandle(handle)
time.sleep(1.0)
kw = {"cwd": root, "stdin": subprocess.DEVNULL}
out = None
if log:
    try:
        out = open(log, "ab")
        kw["stdout"] = out
        kw["stderr"] = out
    except OSError:
        out = None
if os.name == "nt":
    kw["creationflags"] = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW (no console to close by accident) | NEW_PROCESS_GROUP
else:
    kw["start_new_session"] = True
subprocess.Popen(cmd, **kw)
"""

# Waits for the old app to exit, swaps in the checked files and starts the new version (Windows app).
#   -Exe     the exact program that was running (it may be a renamed or downloaded LegacyPlayer-x.y.z-win64.exe): that
#            file is replaced, so the player keeps starting the program they know
#   -Dest    its folder. The program's _internal folder always goes next to it (the app does not start without it);
#            other files from the package (READ ME, LICENSE, VERSION.txt) are only put there when it is the installer's
#            folder (-Installed). The data folder (LegacyPlayerData, data-location.txt) is never touched.
#   -Result  result.json for the app to read when it starts: {ok, tag, error, at}
#   -Manifest / -ManifestSha256  the SHA-256 of every staged file, written when the download was checked, and the
#            manifest's own SHA-256. Before anything is copied, the staged folder must match it exactly (no file changed,
#            added or removed); otherwise the update is abandoned, the staged files are removed and the old app restarts.
# Only the files copied here lose their "downloaded from the internet" mark; nothing else in the folder is touched.
APPLY_PS1 = r"""param([int]$WaitPid, [string]$Stage, [string]$Dest, [string]$Exe, [string]$Tag, [string]$Log, [string]$Result, [string]$Installed,
      [string]$Manifest, [string]$ManifestSha256)
$ErrorActionPreference = 'Stop'
$script:StageBad = $false
function Fail-Stage($why) { $script:StageBad = $true; throw ("The downloaded update changed after it was checked (" + $why + "); nothing was installed.") }
function Test-Stage {
    if (-not $Manifest -or -not $ManifestSha256) { Fail-Stage 'no manifest' }
    if (-not (Test-Path -LiteralPath $Manifest -PathType Leaf)) { Fail-Stage 'manifest missing' }
    if ((Get-FileHash -LiteralPath $Manifest -Algorithm SHA256).Hash -ne $ManifestSha256) { Fail-Stage 'manifest changed' }
    $m = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
    $root = [System.IO.Path]::GetFullPath($Stage).TrimEnd('\') + '\'
    $listed = @{}
    foreach ($e in @($m.files)) {
        $full = [System.IO.Path]::GetFullPath((Join-Path $root ([string]$e.path -replace '/', '\')))
        if (-not $full.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) { Fail-Stage ("outside the folder: " + $e.path) }
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { Fail-Stage ("missing: " + $e.path) }
        if ((Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash -ne [string]$e.sha256) { Fail-Stage ("changed: " + $e.path) }
        $listed[$full.ToLowerInvariant()] = $true
    }
    if ($listed.Count -eq 0) { Fail-Stage 'empty manifest' }
    Get-ChildItem -LiteralPath $Stage -Recurse -Force | ForEach-Object {
        if ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { Fail-Stage ("a link: " + $_.FullName) }
        if (-not $_.PSIsContainer -and -not $listed.ContainsKey($_.FullName.ToLowerInvariant())) { Fail-Stage ("not in the manifest: " + $_.FullName) }
    }
}
function Say($t) { try { Add-Content -LiteralPath $Log -Value ("{0:u}  {1}" -f (Get-Date), $t) } catch {} }
function Done($ok, $err) {
    try {
        $r = [ordered]@{ ok = [bool]$ok; tag = $Tag; error = [string]$err; at = [double]([DateTimeOffset]::UtcNow.ToUnixTimeSeconds()) }
        Set-Content -LiteralPath $Result -Value ($r | ConvertTo-Json -Compress) -Encoding UTF8
    } catch { Say ("Could not write the result: " + $_.Exception.Message) }
}
function SigOf($p) {
    try { $s = Get-AuthenticodeSignature -LiteralPath $p; $subject = ''; if ($s.SignerCertificate) { $subject = [string]$s.SignerCertificate.Subject }; [pscustomobject]@{ Status = [string]$s.Status; Subject = $subject } }
    catch { [pscustomobject]@{ Status = 'Unknown'; Subject = '' } }
}
function Ours { Get-Process -Name $script:ExeName -ErrorAction SilentlyContinue | Where-Object { try { $_.Path -eq $Exe } catch { $false } } }
if (-not $Exe) { $Exe = Join-Path $Dest 'LegacyPlayer.exe' }
$ExeName = [System.IO.Path]::GetFileNameWithoutExtension($Exe)
$ok = $false; $err = ''
$swapped = $false; $exeBackup = "$Exe.old"; $exeBackedUp = $false
$internal = Join-Path $Dest '_internal'
$outgoing = Join-Path $Dest '_internal.old'
try {
    Say "Waiting for Legacy Player ($WaitPid) to close"
    try { Wait-Process -Id $WaitPid -Timeout 90 -ErrorAction SilentlyContinue } catch {}
    # still there after 90 seconds: it asked to be replaced. Only that program is stopped (a process number can be reused by another one).
    $still = Get-Process -Id $WaitPid -ErrorAction SilentlyContinue | Where-Object { try { $_.Path -eq $Exe } catch { $false } }
    if ($still) { Stop-Process -Id $WaitPid -Force -ErrorAction SilentlyContinue }
    # the multiplayer server and friends service run from the same program; they start again with the new version
    Ours | ForEach-Object { Say "Stopping $($_.Id)"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    $until = (Get-Date).AddSeconds(30)
    while ((Ours) -and (Get-Date) -lt $until) { Start-Sleep -Milliseconds 300 }
    Start-Sleep -Milliseconds 500
    Test-Stage                                    # last check, right before anything is copied
    Say "The staged files match the manifest"
    $copied = @()
    # A signed install only accepts an update signed by the same publisher. Without this, whoever could put files on the
    # release page (or in the download's path) could replace a signed program with anything. An unsigned install has
    # nothing to compare with, so it carries on as before.
    $cur = SigOf $Exe
    if ($cur.Status -eq 'Valid') {
        $new = SigOf (Join-Path $Stage 'LegacyPlayer.exe')
        if ($new.Status -ne 'Valid' -or $new.Subject -ne $cur.Subject) {
            throw "This update is not signed by the same publisher as the version you have (it is '$($new.Status)'), so it was not installed. Nothing was changed."
        }
        Say "The update is signed by the same publisher"
    }
    # The app is a folder: LegacyPlayer.exe plus _internal (its libraries). The new _internal is copied next to the old
    # one first, so a failed copy leaves the old app whole; the swap itself is two renames.
    $newInternal = Join-Path $Stage '_internal'
    $incoming = Join-Path $Dest '_internal.new'
    if (Test-Path -LiteralPath $exeBackup) { Remove-Item -LiteralPath $exeBackup -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $newInternal) {
        foreach ($p in @($incoming, $outgoing)) { if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Recurse -Force } }
        Copy-Item -LiteralPath $newInternal -Destination $incoming -Recurse -Force
    }
    # The libraries are swapped first and the program last, and both old copies are kept until everything has worked, so
    # a failure at any step puts the old program and its old libraries back together (a new exe with old libraries does not start).
    if (Test-Path -LiteralPath $incoming) {
        if (Test-Path -LiteralPath $internal) { Move-Item -LiteralPath $internal -Destination $outgoing -Force }
        $swapped = $true
        Move-Item -LiteralPath $incoming -Destination $internal -Force
    }
    if (Test-Path -LiteralPath $Exe) { Copy-Item -LiteralPath $Exe -Destination $exeBackup -Force; $exeBackedUp = $true }
    for ($i = 0; $i -lt 10; $i++) {
        try { Copy-Item -LiteralPath (Join-Path $Stage 'LegacyPlayer.exe') -Destination $Exe -Force; break }
        catch { if ($i -eq 9) { throw }; Start-Sleep 1 }
    }
    $copied += $Exe
    if ($swapped) { $copied += (Get-ChildItem -LiteralPath $internal -Recurse -File | ForEach-Object { $_.FullName }) }
    Remove-Item -LiteralPath $outgoing -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $exeBackup -Force -ErrorAction SilentlyContinue
    $inInstalled = $false
    if ($Installed) {
        try {
            $a = [System.IO.Path]::GetFullPath($Dest).TrimEnd('\')
            $b = [System.IO.Path]::GetFullPath($Installed).TrimEnd('\')
            $inInstalled = ($a -ieq $b)
        } catch {}
    }
    if ($inInstalled) {
        Get-ChildItem -LiteralPath $Stage -Force | Where-Object { $_.Name -ne 'LegacyPlayer.exe' -and $_.Name -ne '_internal' } | ForEach-Object {
            $target = Join-Path $Dest $_.Name
            Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
            if ($_.PSIsContainer) { $copied += (Get-ChildItem -LiteralPath $target -Recurse -File | ForEach-Object { $_.FullName }) }
            else { $copied += $target }
        }
        $versionFile = Join-Path $Dest 'VERSION.txt'
        Set-Content -LiteralPath $versionFile -Value $Tag -Encoding ASCII
    }
    foreach ($f in $copied) { try { Unblock-File -LiteralPath $f -ErrorAction SilentlyContinue } catch {} }
    Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
    if ($Manifest) { Remove-Item -LiteralPath $Manifest -Force -ErrorAction SilentlyContinue }
    Say "Installed $Tag into $Exe; starting it"
    $ok = $true
} catch {
    $err = $_.Exception.Message
    Say ("The update did not finish: " + $err)
    try {      # put the old program and its old libraries back, so the app that starts below is whole
        if ($swapped) {
            if (Test-Path -LiteralPath $internal) { Remove-Item -LiteralPath $internal -Recurse -Force -ErrorAction SilentlyContinue }
            if (Test-Path -LiteralPath $outgoing) { Move-Item -LiteralPath $outgoing -Destination $internal -Force }
        }
        if ($exeBackedUp -and (Test-Path -LiteralPath $exeBackup)) { Copy-Item -LiteralPath $exeBackup -Destination $Exe -Force; Remove-Item -LiteralPath $exeBackup -Force -ErrorAction SilentlyContinue }
    } catch { Say ("Could not put the old version back: " + $_.Exception.Message) }
    if ($script:StageBad) {                       # never leave files that failed the check where a later run could use them
        Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
        if ($Manifest) { Remove-Item -LiteralPath $Manifest -Force -ErrorAction SilentlyContinue }
    }
}
Done $ok $err
try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe                       # no wildcard parsing here, so folders with [ ] work
    $psi.WorkingDirectory = $Dest
    $psi.UseShellExecute = $true
    [void][System.Diagnostics.Process]::Start($psi)
} catch { Say ("Could not start Legacy Player again: " + $_.Exception.Message) }
"""

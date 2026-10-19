"""Open Legacy Player in its own app-style window (no address bar or tabs) using the Edge or
Chrome already on the computer, so the downloadable app feels like a normal program.
The window is just a viewer: closing it ends the app (the page sends a heartbeat)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from .childenv import child_cwd, clean_env


def find_app_browser() -> str | None:
    candidates: list[str] = []
    if sys.platform == "win32":
        for var in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
            base = os.environ.get(var)
            if base:
                candidates += [
                    str(Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
                    str(Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"),
                ]
    elif sys.platform == "darwin":
        candidates += ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                       "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for exe in candidates:
        if Path(exe).is_file():
            return exe
    for name in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def app_window_command(browser: str, url: str, profile_dir: Path, fullscreen: bool = False, platform: str | None = None) -> list[str]:
    """The app-style window. fullscreen (TV mode is the start page): the window opens full screen by itself, because a
    page can only go full screen after a click or key press and a controller press does not count. On Windows the app
    makes its own window full screen instead (launcher/winplace.py, which TV mode can also undo when it is left), so the
    flag is only added elsewhere."""
    cmd = [browser, f"--app={url}", f"--user-data-dir={profile_dir}", "--no-first-run",
           "--no-default-browser-check", "--window-size=1280,860"]
    if fullscreen and (platform or sys.platform) != "win32":
        cmd.append("--start-fullscreen")
    return cmd


def opens_in_tv_mode(settings: dict) -> bool:
    """Will the page open TV mode at start-up? (the start page is TV mode, or the last page used was TV mode; never on
    the very first start, which shows the welcome steps)"""
    if not settings.get("setup_done"):
        return False
    page = settings.get("start_page") or "home"
    if page == "last":
        page = settings.get("last_page") or "home"
    return page in ("tv", "console")


def make_opener(data_dir: Path, fullscreen=None):
    """fullscreen: optional callable answering whether the window should open full screen (see opens_in_tv_mode)."""
    def opener(url: str) -> None:
        browser = find_app_browser()
        if browser:
            try:
                full = False
                try:
                    full = bool(fullscreen()) if fullscreen else False
                except Exception:          # a settings problem must never stop the window from opening
                    full = False
                subprocess.Popen(app_window_command(browser, url, Path(data_dir) / "window_profile", fullscreen=full),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 cwd=child_cwd(data_dir), env=clean_env())    # never inside the exe's temporary folder
                return
            except OSError:
                pass
        webbrowser.open(url)  # still works; the page's heartbeat ends the app when the tab closes
    return opener


def make_overlay_opener(data_dir: Path):
    """A small, separate window for the in-game overlay (its own browser profile, so it never touches the main window)."""
    def opener(url: str) -> bool:
        browser = find_app_browser()
        if not browser:
            return False
        try:
            subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={Path(data_dir) / 'overlay_profile'}", "--no-first-run",
                              "--no-default-browser-check", "--window-size=400,600"],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             cwd=child_cwd(data_dir), env=clean_env())
            return True
        except OSError:
            return False
    return opener

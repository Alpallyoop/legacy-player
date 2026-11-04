"""Let friends through the Windows Firewall for the server port, once, on every kind of network.

Without a rule Windows asks the first time and usually offers only "private networks", which silently blocks a computer
that Windows has labelled "public" (hotspots, hotels). Adding the rule needs administrator rights, so when the app is not
elevated it asks Windows for the usual approval box (the player sees one prompt and presses Yes). Windows only; on other
systems everything here says "not needed".
"""
from __future__ import annotations

import base64
import re
import subprocess
import sys
from pathlib import Path

RULE = "Legacy Player server"
RULE_FRIENDS = "Legacy Player friends service"
_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def supported() -> bool:
    return sys.platform == "win32"


def _run(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, creationflags=_FLAGS)


def rule_args(port: int, program: str | None = None, rule: str = RULE) -> list[str]:
    """Every network profile on purpose (hotspots count as "public"), but when the app is the packaged exe the rule
    only lets that one program accept connections, not whatever else might listen on the port."""
    if program is None and getattr(sys, "frozen", False):
        program = sys.executable
    args = ["advfirewall", "firewall", "add", "rule", f"name={rule}", "dir=in", "action=allow", "protocol=TCP",
            f"localport={int(port)}", "profile=any"]
    if program:
        args.append(f"program={program}")
    return args


def _ps_quote(text: str) -> str:
    """A PowerShell single-quoted literal: nothing inside is expanded; a ' is doubled."""
    return "'" + str(text).replace("'", "''") + "'"


# Absolute paths, so neither the elevated process nor the one asking for it can be handed a planted powershell.exe or
# netsh.exe from the current folder or PATH. %SystemRoot% is expanded by PowerShell itself.
# Written as (Join-Path ...) with single quotes so no double quote has to survive the Windows command line.
_NETSH = "(Join-Path $env:SystemRoot 'System32\\netsh.exe')"
_POWERSHELL = "(Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe')"


def elevated_script(args: list[str], before: tuple = ()) -> str:
    """What runs as administrator: the netsh commands, each argument a literal, and the LAST command's exit code as the
    process exit code (so success does not depend on the language of netsh's messages)."""
    lines = ["$ErrorActionPreference = 'Continue'"]
    for a in before:
        lines.append(f"& {_NETSH} {' '.join(_ps_quote(x) for x in a)} | Out-Null")
    lines.append(f"& {_NETSH} {' '.join(_ps_quote(x) for x in args)} | Out-Null")
    lines.append("exit $LASTEXITCODE")
    return "\n".join(lines)


def _encoded(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _elevated(args: list[str], run, before: tuple = ()) -> dict:
    """Run netsh as administrator through the Windows approval box and report what happened. One approval covers everything:
    the commands in `before` (for example deleting an old rule) and then `args`.
    Everything the elevated process runs is inside its own command line (-EncodedCommand, UTF-16 so a path such as
    C:\\Users\\José stays intact): there is no script or log file another program could swap before the approval box is
    answered. The elevated process's exit code is netsh's exit code for the LAST command; netsh's own words cannot be
    carried back without a file, so a failure reports that code. Returns {"cancelled", "ok", "log", "error"}."""
    inner = ", ".join(_ps_quote(x) for x in ("-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                                             "-EncodedCommand", _encoded(elevated_script(args, before))))
    outer = (f"$p = Start-Process -FilePath {_POWERSHELL} -ArgumentList {inner} -Verb RunAs -Wait -PassThru "
             "-WindowStyle Hidden; if ($p) { 'LP_EXIT=' + $p.ExitCode }")
    result = run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", outer], timeout=120)
    err = str(getattr(result, "stderr", "") or "").strip()
    out = str(getattr(result, "stdout", "") or "")
    code = re.search(r"LP_EXIT=(-?\d+)", out)
    ok = bool(code) and code.group(1) == "0"
    log = "" if ok or not code else f"netsh ended with code {code.group(1)}."
    return {"cancelled": ("cancel" in err.lower()) and not code, "ok": ok, "log": log, "error": err[:300]}


def manual_command(port: int, rule: str = RULE) -> str:
    """What to paste into an administrator PowerShell if the approval box does not work."""
    return (f'netsh advfirewall firewall delete rule name="{rule}"; '
            f'netsh advfirewall firewall add rule name="{rule}" dir=in action=allow protocol=TCP localport={int(port)} profile=any')


def _program_matches(program: str, text: str) -> bool:
    """The rule is fine when it names this program (by file name, so path spelling cannot matter) or names no program at all
    ("Any", in any language), as a rule added by hand does. A rule for a different program does not count."""
    m = re.search(r"^\s*Program:\s*(.+?)\s*$", text, re.M)
    if m is None:
        return True          # Windows prints no Program line at all for a rule that is not tied to a program (as one added by hand)
    if not re.search(r"[\\/]|\.exe", m.group(1), re.I):
        return True          # "Any" in whatever language
    return Path(program).name.lower() in m.group(1).lower()


def status(port: int, run=_run, rule: str = RULE) -> dict:
    if not supported():
        return {"supported": False, "allowed": True, "message": "Not needed on this system."}
    try:
        out = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule}"])
    except (OSError, subprocess.SubprocessError):
        return {"supported": True, "allowed": False, "message": "Could not read the Windows Firewall."}
    text = out.stdout or ""
    ports = re.findall(r"^\s*LocalPort:\s*(\S+)", text, re.M)          # exact port, not a substring (87 must not match 8765); other Windows languages: bare number
    port_ok = str(int(port)) in [x.strip() for x in ports] or (not ports and re.search(rf"(?<!\d){int(port)}(?!\d)", text) is not None)
    program = rule_args(port, rule=rule)[-1][len("program="):] if rule_args(port, rule=rule)[-1].startswith("program=") else ""
    program_ok = (not program) or _program_matches(program, text)
    allowed = out.returncode == 0 and port_ok and program_ok
    return {"supported": True, "allowed": allowed, "seen": {"found": out.returncode == 0, "port_ok": port_ok, "program_ok": program_ok},
            "message": "Windows Firewall already lets friends in." if allowed else "Windows Firewall has no rule for your server yet."}


def allow(port: int, run=_run, rule: str = RULE) -> dict:
    """Add the rule, asking Windows for approval when not already an administrator."""
    if not supported():
        return {"supported": False, "allowed": True, "message": "Not needed on this system."}
    already = status(port, run, rule)
    if already["allowed"]:
        return already
    detail: dict = {}
    delete_args = ["advfirewall", "firewall", "delete", "rule", f"name={rule}"]
    try:
        old_rule_stays = False
        if exists(run, rule):          # an old rule for another port or program would never match: replace it, do not pile up copies
            old_rule_stays = run(["netsh"] + delete_args).returncode != 0
        direct = None if old_rule_stays else run(["netsh"] + rule_args(port, rule=rule))
        if direct is None or direct.returncode != 0:
            detail = _elevated(rule_args(port, rule=rule), run, before=(delete_args,) if old_rule_stays else ()) or {}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"supported": True, "allowed": False, "message": f"Windows did not allow the change ({exc}).", "manual": manual_command(port, rule)}
    now = status(port, run, rule)
    if now["allowed"] or detail.get("ok"):
        # netsh itself said it worked (exit code 0): believe it even if reading the rule back is picky
        now["allowed"] = True
        now["message"] = "Done. Windows Firewall now lets friends connect to your server."
        return now
    if detail.get("cancelled"):
        why = "You closed or refused the Windows approval box."
    elif detail.get("log"):
        why = f"Windows said: {detail['log']}"
    elif detail.get("error"):
        why = f"Windows said: {detail['error']}"
    else:
        why = "Windows did not report a reason."
    now["message"] = f"The rule was not added. {why} Friends on other networks may be blocked."
    now["manual"] = manual_command(port, rule)
    return now


def exists(run=_run, rule: str = RULE) -> bool:
    """Is there a Legacy Player rule in the Windows Firewall at all."""
    if not supported():
        return False
    try:
        out = run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule}"])
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and rule in (out.stdout or "")


def remove(run=_run) -> dict:
    """Take the rules away again (used by the uninstaller). Asks Windows for approval when not already an administrator."""
    if not supported():
        return {"removed": True}
    for rule in (RULE, RULE_FRIENDS):
        args = ["advfirewall", "firewall", "delete", "rule", f"name={rule}"]
        try:
            if exists(run, rule) and run(["netsh"] + args).returncode != 0 and exists(run, rule):
                _elevated(args, run)
        except (OSError, subprocess.SubprocessError):
            pass
    return {"removed": not exists(run) and not exists(run, RULE_FRIENDS)}

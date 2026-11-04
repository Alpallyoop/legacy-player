"""Regression tests for the 2026-11-04 audit fixes (docs/audits/AUDIT_2026-11-04.md): CI supply chain, the firewall
approval, the staged self-update, DAT parsing, game-card look-ups, archive tools and the server deployment files.
(UPnP is covered in tests/test_portmap.py.)"""
import base64
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from launcher import datfiles, firewall, gamecard, selfupdate, setup

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def text(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def run_blocks(wf: str) -> list[str]:
    """The body of every `run: |` block (and one-line `run:`) in a workflow."""
    blocks, lines, i = [], wf.splitlines(), 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", lines[i])
        if not m:
            i += 1
            continue
        indent, rest = len(m.group(1)), m.group(2)
        if rest.strip() in ("|", ">", "|-", ">-"):
            body, i = [], i + 1
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
                body.append(lines[i])
                i += 1
            blocks.append("\n".join(body))
        else:
            blocks.append(rest)
            i += 1
    return blocks


def strip_comments(wf: str) -> str:
    return "\n".join(line for line in wf.splitlines() if not line.lstrip().startswith("#"))


def jobs(wf: str) -> dict[str, str]:
    """job name -> its text without comment lines (jobs are the two-space keys under `jobs:`)."""
    wf = strip_comments(wf)
    body = wf[wf.index("\njobs:\n"):]
    parts = re.split(r"\n  (?=[A-Za-z0-9_-]+:\n)", body)
    return {p.split(":", 1)[0].strip(): p for p in parts[1:]}


class WorkflowTests(unittest.TestCase):
    def test_there_are_workflows(self):
        self.assertTrue(WORKFLOWS)

    def test_no_expression_is_pasted_into_a_script(self):
        for wf in WORKFLOWS:
            for block in run_blocks(wf.read_text(encoding="utf-8")):
                self.assertNotIn("${{", block, f"{wf.name}: pass it through env: instead\n{block[:200]}")

    def test_every_action_is_pinned_to_a_commit(self):
        for wf in WORKFLOWS:
            for line in wf.read_text(encoding="utf-8").splitlines():
                m = re.search(r"uses:\s*(\S+)", line)
                if m and not m.group(1).startswith("./"):
                    self.assertRegex(m.group(1), r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$", f"{wf.name}: {line.strip()}")
                    self.assertRegex(line, r"#\s*v\d", f"{wf.name}: say which tag the SHA is: {line.strip()}")

    def test_checkout_never_keeps_the_token(self):
        for wf in WORKFLOWS:
            s = wf.read_text(encoding="utf-8")
            self.assertEqual(s.count("actions/checkout@"), s.count("persist-credentials: false"), wf.name)

    def test_permissions_are_read_only_unless_a_job_says_otherwise(self):
        for wf in WORKFLOWS:
            s = wf.read_text(encoding="utf-8")
            top = s[:s.index("\njobs:\n")]
            self.assertRegex(top, r"\npermissions:\n  contents: read\n", wf.name)
            self.assertNotIn(": write", top, wf.name)

    def test_only_the_publish_job_can_write_and_it_runs_no_repository_code(self):
        wf = text(".github/workflows/release.yml")
        j = jobs(wf)
        self.assertEqual({"build", "sign-package", "smoke", "publish"}, set(j))
        for name, body in j.items():
            if name == "publish":
                continue
            self.assertNotIn("contents: write", body, name)
            self.assertNotIn("attestations: write", body, name)
        self.assertNotIn("id-token: write", j["build"])
        self.assertNotIn("id-token: write", j["smoke"])
        self.assertNotIn("secrets.", j["build"] + j["smoke"])
        pub = j["publish"]
        self.assertIn("contents: write", pub)
        self.assertNotIn("actions/checkout", pub)
        self.assertNotIn("pip install", pub)
        self.assertNotIn("./tools/", pub)
        self.assertIn("startsWith(github.ref, 'refs/tags/v')", pub)
        self.assertIn("needs: [sign-package, smoke]", pub)          # never publishes what the smoke check did not start

    def test_tag_names_reach_scripts_only_through_the_environment(self):
        wf = text(".github/workflows/release.yml")
        self.assertIn("TAG: ${{ github.ref_name }}", wf)
        self.assertIn("$env:TAG", wf)

    def test_ci_installs_with_hashes_only(self):
        for wf in WORKFLOWS:
            for line in strip_comments(wf.read_text(encoding="utf-8")).splitlines():
                if "pip install" in line:
                    self.assertIn("--require-hashes", line, f"{wf.name}: {line.strip()}")


def requirements(path: Path) -> list[tuple[str, list[str]]]:
    joined = re.sub(r"\\\n", " ", path.read_text(encoding="utf-8"))
    out = []
    for line in joined.splitlines():
        line = line.split("#", 1)[0].strip() if not line.lstrip().startswith("--hash") else line.strip()
        if not line:
            continue
        spec = line.split()[0]
        out.append((spec, re.findall(r"--hash=sha256:([0-9a-f]{64})", line)))
    return out


class RequirementsTests(unittest.TestCase):
    def test_every_requirement_is_pinned_and_hashed(self):
        for rel in ("tools/memory_probe/requirements.txt", "requirements-build.txt"):
            reqs = requirements(ROOT / rel)
            self.assertTrue(reqs, rel)
            for spec, hashes in reqs:
                self.assertRegex(spec, r"^[A-Za-z0-9._-]+==[0-9][0-9A-Za-z.]*$", f"{rel}: {spec}")
                self.assertTrue(hashes, f"{rel}: {spec} has no hash")

    def test_the_build_lock_covers_pyinstaller_and_its_windows_dependencies(self):
        names = {s.split("==")[0].lower() for s, _ in requirements(ROOT / "requirements-build.txt")}
        self.assertLessEqual({"pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "packaging", "pefile", "pywin32-ctypes",
                              "setuptools", "psutil"}, names)

    def test_build_script_installs_from_the_lock(self):
        bat = text("build_exe.bat")
        self.assertIn("pip install --require-hashes -r requirements-build.txt", bat)
        self.assertNotRegex(bat, r"pip install[^\n]*(pyinstaller|psutil)==")


def decoded(cmd) -> str:
    b64 = re.search(r"'-EncodedCommand', '([A-Za-z0-9+/=]+)'", cmd[-1]).group(1)
    return base64.b64decode(b64).decode("utf-16-le")


class FirewallElevationTests(unittest.TestCase):
    def test_no_file_is_written_and_everything_is_on_the_command_line(self):
        seen = {}

        def run(cmd, timeout=0):
            seen["cmd"] = cmd
            return mock.Mock(stderr="", stdout="LP_EXIT=0\r\n")
        boom = mock.Mock(side_effect=AssertionError("no file for the elevated run"))
        with mock.patch("tempfile.mkdtemp", boom), mock.patch("tempfile.mkstemp", boom), \
                mock.patch("tempfile.NamedTemporaryFile", boom), mock.patch("builtins.open", boom):
            out = firewall._elevated(firewall.rule_args(8765, "C:\\Users\\José\\Apps\\LP\\LegacyPlayer.exe"), run)
        self.assertTrue(out["ok"])
        outer = seen["cmd"][-1]
        self.assertIn("-Verb RunAs", outer)
        self.assertIn("'-EncodedCommand'", outer)
        self.assertIn("Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe'", outer)
        self.assertNotRegex(outer, r"\.cmd\b|\.ps1\b")
        script = decoded(seen["cmd"])
        self.assertIn("'program=C:\\Users\\José\\Apps\\LP\\LegacyPlayer.exe'", script)       # not mangled to Jos?
        self.assertIn("Join-Path $env:SystemRoot 'System32\\netsh.exe'", script)
        self.assertTrue(script.rstrip().endswith("exit $LASTEXITCODE"))

    def test_arguments_are_literals_even_with_quotes_and_dollars(self):
        script = firewall.elevated_script(["advfirewall", "firewall", "add", "rule", "name=O'Brien $(calc) `x"])
        self.assertIn("'name=O''Brien $(calc) `x'", script)

    def test_before_commands_share_the_one_approval(self):
        delete = ["advfirewall", "firewall", "delete", "rule", "name=Legacy Player server"]
        script = firewall.elevated_script(firewall.rule_args(1, "C:\\x.exe"), (delete,))
        self.assertEqual(2, script.count("netsh.exe"))
        self.assertLess(script.index("'delete'"), script.index("'add'"))

    def test_failure_code_and_cancel_are_reported(self):
        out = firewall._elevated(["x"], lambda c, timeout=0: mock.Mock(stderr="", stdout="LP_EXIT=1"))
        self.assertEqual((False, False, "netsh ended with code 1."), (out["ok"], out["cancelled"], out["log"]))
        out = firewall._elevated(["x"], lambda c, timeout=0: mock.Mock(stderr="The operation was canceled by the user.", stdout=""))
        self.assertTrue(out["cancelled"])
        self.assertFalse(out["ok"])

    def test_the_module_has_no_script_file_left(self):
        src = text("launcher/firewall.py")
        self.assertNotIn("lp-firewall.cmd", src)
        self.assertNotIn("import tempfile", src)
        self.assertNotIn('encoding="ascii"', src)


class StagedUpdateManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def fake_release(self):
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("LegacyPlayer.exe", b"MZ new")
            z.writestr("_internal/lib.dll", b"lib")
            z.writestr("_internal/sub/é.txt", b"accent")
        data = buf.getvalue()
        files = {"zip": data, "sum": (hashlib.sha256(data).hexdigest() + "  x.zip\n").encode()}
        rel = {"tag": "v99.0.0", "page": "p", "assets": [
            {"name": "LegacyPlayer-99.0.0-win64.zip", "url": "https://github.com/z", "size": len(data), "sha256": ""},
            {"name": "LegacyPlayer-99.0.0-win64.zip.sha256", "url": "https://github.com/s", "size": 90, "sha256": ""}]}

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        return rel, (lambda url, hosts, allow_http=False, timeout=30: Resp(files["zip"] if url.endswith("/z") else files["sum"]))

    def prepared(self):
        up = selfupdate.SelfUpdate(self.tmp / "data")
        up.mode = lambda: "exe"
        rel, opener = self.fake_release()
        (self.tmp / "app").mkdir()
        with mock.patch.object(selfupdate, "_open", opener), mock.patch.object(selfupdate.sys, "platform", "win32"), \
                mock.patch.object(selfupdate.sys, "executable", str(self.tmp / "app" / "LegacyPlayer.exe")):
            up.prepare({"mode": "exe", "newer": True, "latest": rel["tag"], "release": rel, "message": ""})
            plan = up.restart_plan()
        return up, plan

    def test_staging_records_every_file_and_the_plan_carries_the_manifest_hash(self):
        up, plan = self.prepared()
        stage, manifest = Path(up.staged["stage"]), Path(up.staged["manifest"])
        self.assertEqual(stage.parent, manifest.parent)                   # beside the staged folder, never copied with it
        raw = manifest.read_bytes()
        listed = {e["path"]: e["sha256"] for e in json.loads(raw)["files"]}
        on_disk = {p.relative_to(stage).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob("*") if p.is_file()}
        self.assertEqual(on_disk, listed)
        self.assertIn("_internal/sub/é.txt", listed)
        self.assertEqual(str(manifest), plan[plan.index("-Manifest") + 1])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), plan[plan.index("-ManifestSha256") + 1])

    def test_a_plan_without_a_manifest_hash_cannot_pass_the_check(self):
        up = selfupdate.SelfUpdate(self.tmp)
        up.staged = {"mode": "exe", "version": "v1", "stage": str(self.tmp / "update" / "new"), "dest": str(self.tmp),
                     "exe": str(self.tmp / "x.exe")}
        plan = up.restart_plan()
        self.assertEqual("", plan[plan.index("-ManifestSha256") + 1])
        self.assertIn("if (-not $Manifest -or -not $ManifestSha256) { Fail-Stage", selfupdate.APPLY_PS1)

    def test_links_in_the_stage_are_refused(self):
        stage = self.tmp / "new"
        stage.mkdir()
        (stage / "LegacyPlayer.exe").write_bytes(b"x")
        try:
            (stage / "link").symlink_to(stage / "LegacyPlayer.exe")
        except (OSError, NotImplementedError):
            self.skipTest("cannot make a link here")
        with self.assertRaises(selfupdate.InstallError):
            selfupdate.write_stage_manifest(stage, self.tmp / "manifest.json")

    def test_apply_checks_the_stage_before_copying_anything_and_cleans_up_on_mismatch(self):
        s = selfupdate.APPLY_PS1
        body = s[s.index("try {\n    Say \"Waiting"):]
        self.assertLess(body.index("Test-Stage"), body.index("Copy-Item"))
        test_stage = s[s.index("function Test-Stage"):s.index("\n}\n", s.index("function Test-Stage"))]
        for needle in ("Get-FileHash -LiteralPath $Manifest -Algorithm SHA256", "Get-FileHash -LiteralPath $full -Algorithm SHA256",
                       "not in the manifest", "ReparsePoint", "OrdinalIgnoreCase"):
            self.assertIn(needle, test_stage)
        catch = s[s.index("} catch {\n    $err"):]
        self.assertIn("if ($script:StageBad)", catch)
        self.assertIn("Remove-Item -LiteralPath $Stage -Recurse -Force", catch)
        self.assertIn("Remove-Item -LiteralPath $Manifest -Force", catch)

    def test_the_signature_is_checked_before_unpacking(self):
        src = text("launcher/selfupdate.py")                 # signing itself: tests/test_update_signing.py
        self.assertLess(src.index("signature_ok(_version.UPDATE_SIGNING_KEYS"), src.index("extract_zip_safe(archive, stage)"))


DAT_BOMB = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE d [<!ENTITY a "AAAA">]>'
            '<datafile><game name="&a;"><rom name="r" size="1" crc="00000000"/></game></datafile>')
DAT_OK = ('<?xml version="1.0" encoding="UTF-16"?>\n<!DOCTYPE datafile PUBLIC "-//Logiqx//DTD ROM Management Datafile//EN" '
          '"http://www.logiqx.com/Dats/datafile.dtd">\n<datafile><game name="Söme Game (World)"><rom name="r" size="1" '
          'crc="00000000"/></game></datafile>')


class DatEncodingTests(unittest.TestCase):
    def test_entities_are_refused_in_every_utf16_spelling(self):
        for enc in ("utf-16", "utf-16-le", "utf-16-be"):
            with self.assertRaises(datfiles.DatError, msg=enc):
                datfiles._parse_logiqx(DAT_BOMB.encode(enc))

    def test_a_utf16_dat_file_with_entities_is_refused_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.dat"
            p.write_bytes(DAT_BOMB.encode("utf-16-le"))                 # no BOM: starts with '<', so it is read as XML
            with self.assertRaises(datfiles.DatError):
                datfiles.parse_dat(p)

    def test_an_internal_subset_without_entities_is_refused_in_utf16(self):
        x = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE d [<!ELEMENT d ANY>]><datafile/>'
        with self.assertRaises(datfiles.DatError):
            datfiles._parse_logiqx(x.encode("utf-16"))

    def test_a_plain_utf16_dat_with_an_external_doctype_still_reads(self):
        out = datfiles._parse_logiqx(DAT_OK.encode("utf-16-le"))
        self.assertEqual("Söme Game (World)", out["games"][0]["name"])


class _Req:
    full_url = "https://en.wikipedia.org/w/api.php"


class GameCardRedirectTests(unittest.TestCase):
    def test_redirects_off_the_wiki_hosts_or_to_http_are_refused(self):
        h = gamecard._OnlyWiki()
        req = urllib.request.Request("https://en.wikipedia.org/w/api.php")
        for bad in ("https://evil.example/x", "http://en.wikipedia.org/x", "file:///etc/passwd", "ftp://www.wikidata.org/x",
                    "https://user@en.wikipedia.org/x"):
            with self.assertRaises(urllib.error.URLError, msg=bad):
                h.redirect_request(req, None, 302, "Found", {}, bad)
        ok = h.redirect_request(req, None, 302, "Found", {}, "https://www.wikidata.org/wiki/Special:EntityData/Q1.json")
        self.assertEqual("www.wikidata.org", urllib.parse.urlsplit(ok.full_url).hostname)
        rel = h.redirect_request(req, None, 301, "Moved", {}, "/wiki/Other")           # relative: same https host
        self.assertEqual("https://en.wikipedia.org/wiki/Other", rel.full_url)

    def test_plain_http_is_refused_before_anything_is_sent(self):
        with self.assertRaises(ValueError):
            gamecard._get_json("http://en.wikipedia.org/w/api.php", opener=mock.Mock(side_effect=AssertionError("sent")))

    def test_the_default_opener_checks_redirects(self):
        seen = {}

        def fake_open(request, timeout=12):
            seen["url"] = request.full_url
            return io.BytesIO(b"{}")
        with mock.patch.object(gamecard, "_open", fake_open):
            gamecard._get_json("https://en.wikipedia.org/w/api.php?x=1")
        self.assertIn("en.wikipedia.org", seen["url"])
        self.assertIsNone(gamecard.CardLookups(Path(tempfile.gettempdir())).opener)      # falls back to the checked opener
        self.assertIn(gamecard._OnlyWiki, [type(h) for h in urllib.request.build_opener(gamecard._OnlyWiki()).handlers])


class ArchiveToolLookupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.here, self.other = self.tmp / "here", self.tmp / "bin"
        for d in (self.here, self.other):
            d.mkdir()
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.here)

    def tool(self, folder, name):
        p = folder / (name + (".exe" if sys.platform == "win32" else ""))
        p.write_text("#!/bin/sh\n")
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
        return p

    def test_the_current_folder_is_never_used(self):
        self.tool(self.here, "7z")
        for path in (".", "", str(self.here), "relative/bin", f".{os.pathsep}{self.here}"):
            with mock.patch.dict(os.environ, {"PATH": path}):
                self.assertIsNone(setup._which_absolute("7z"), path)

    def test_a_real_path_entry_gives_an_absolute_program(self):
        self.tool(self.here, "7z")
        real = self.tool(self.other, "7z")
        with mock.patch.dict(os.environ, {"PATH": os.pathsep.join([".", str(self.here), str(self.other)])}):
            found = setup._which_absolute("7z")
        self.assertEqual(os.path.normcase(str(real)), os.path.normcase(found))
        self.assertTrue(os.path.isabs(found))

    def test_every_tool_found_is_absolute_and_known_places_come_first(self):
        self.tool(self.other, "7z")
        self.tool(self.other, "tar")
        known = self.tmp / "pf" / "7-Zip" / "7z.exe"
        known.parent.mkdir(parents=True)
        known.write_text("x")
        with mock.patch.dict(os.environ, {"PATH": str(self.other)}), \
                mock.patch.object(setup, "_known_7z_paths", return_value=[str(known)]):
            tools = setup._seven_zip_tools()
        self.assertEqual(("7z", str(known)), tools[0])
        self.assertTrue(all(os.path.isabs(p) for _, p in tools), tools)
        self.assertIn("tar", [k for k, _ in tools])

    def test_windows_prefers_system32_tar(self):
        sysroot = self.tmp / "Windows"
        (sysroot / "System32").mkdir(parents=True)
        (sysroot / "System32" / "tar.exe").write_text("x")
        with mock.patch.dict(os.environ, {"SystemRoot": str(sysroot)}):
            self.assertEqual(str(sysroot / "System32" / "tar.exe"), setup._system_tar())


class DeployTests(unittest.TestCase):
    def test_caddy_keeps_only_the_port_binding_capability(self):
        compose = text("deploy/docker-compose.yml")
        https = compose[compose.index("  https:"):compose.index("\nvolumes:")]
        self.assertIn("cap_drop: [ALL]", https)
        self.assertIn("cap_add: [NET_BIND_SERVICE]", https)
        self.assertIn("no-new-privileges:true", https)

    def test_the_systemd_unit_is_sandboxed(self):
        unit = text("deploy/legacy-player-server.service")
        for line in ("CapabilityBoundingSet=\n", "AmbientCapabilities=\n", "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
                     "SystemCallFilter=@system-service", "SystemCallArchitectures=native", "ProtectKernelTunables=yes",
                     "ProtectKernelModules=yes", "ProtectKernelLogs=yes", "ProtectControlGroups=yes", "ProtectClock=yes",
                     "ProtectHostname=yes", "LockPersonality=yes", "MemoryDenyWriteExecute=yes", "RestrictNamespaces=yes",
                     "RestrictRealtime=yes", "RestrictSUIDSGID=yes", "PrivateDevices=yes", "UMask=0077", "MemoryMax=",
                     "NoNewPrivileges=true", "ProtectSystem=strict", "ReadWritePaths=/var/lib/legacy-player"):
            self.assertIn(line, unit)
        self.assertIn("--port 8765", unit)                                   # setup-vps.sh rewrites exactly this

    def test_setup_installs_a_release_tag_by_default(self):
        sh = text("deploy/setup-vps.sh")
        self.assertIn('REF="${LP_REF:-}"', sh)
        self.assertIn("git ls-remote --tags --refs", sh)
        self.assertIn("sort -V", sh)
        self.assertIn("checkout -q --detach FETCH_HEAD", sh)
        self.assertNotIn("pull --ff-only", sh)
        self.assertRegex(sh, r'\[\[ "\$PORT" =~ \^\[0-9\]')                   # the port is checked before it reaches sed
        self.assertIn("CAP_NET_BIND_SERVICE", sh)                           # only for a port below 1024


if __name__ == "__main__":
    unittest.main()

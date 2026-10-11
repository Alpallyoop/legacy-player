"""Steam and Epic detection (registry, libraryfolders.vdf old and new, appmanifest, Epic .item), games hidden inside Steam
(collections JSON and the older VDF files), and what the doctor says about PC games and the last computer scan."""
import base64
import json
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from launcher import pcgames, pcscan
from launcher.app import LauncherApp


def _jpeg(w: int, h: int, tail: bytes = b"") -> bytes:
    sof = b"\xff\xc0" + (11).to_bytes(2, "big") + b"\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big") + b"\x01\x01\x11\x00"
    return b"\xff\xd8\xff\xe0\x00\x02" + sof + b"\xff\xd9" + tail


def vdf_path(p: Path) -> str:
    return str(p).replace("\\", "\\\\")            # how Steam writes a path inside a VDF file


def acf(appid: str, name: str, flags: str = "4", size: str = "1000") -> str:
    return ('"AppState"\n{\n\t"appid"\t\t"%s"\n\t"Universe"\t\t"1"\n\t"name"\t\t"%s"\n\t"StateFlags"\t\t"%s"\n'
            '\t"installdir"\t\t"%s"\n\t"SizeOnDisk"\t\t"%s"\n\t"UserConfig"\n\t{\n\t\t"language"\t\t"english"\n\t}\n}\n') % (appid, name, flags, name, size)


def make_steam(base: Path, new_format: bool = True) -> Path:
    root = base / "Steam"
    (root / "steamapps").mkdir(parents=True)
    (root / "steam.exe").write_bytes(b"MZ")
    lib2 = base / "D drive" / "SteamLibrary"
    (lib2 / "steamapps").mkdir(parents=True)
    if new_format:
        text = ('"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t\t"label"\t\t""\n\t\t"contentid"\t\t"123"\n\t\t"apps"\n\t\t{\n'
                '\t\t\t"620"\t\t"1000"\n\t\t}\n\t}\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t\t"label"\t\t"Games"\n\t\t"apps"\n\t\t{\n\t\t}\n\t}\n}\n'
                % (vdf_path(root), vdf_path(lib2)))
    else:
        text = '"LibraryFolders"\n{\n\t"TimeNextStatsReport"\t\t"1700000000"\n\t"ContentStatsID"\t\t"-123"\n\t"1"\t\t"%s"\n}\n' % vdf_path(lib2)
    (root / "steamapps" / "libraryfolders.vdf").write_text(text, encoding="utf-8")
    (root / "steamapps" / "appmanifest_620.acf").write_text(acf("620", "Portal 2"), encoding="utf-8")
    (lib2 / "steamapps" / "appmanifest_1145360.acf").write_text("\ufeff" + acf("1145360", "Hades"), encoding="utf-8")
    (lib2 / "steamapps" / "appmanifest_1091500.acf").write_text(acf("1091500", "サイバーパンク2077 Ünïcødé"), encoding="utf-8")
    (root / "steamapps" / "appmanifest_228980.acf").write_text(acf("228980", "Steamworks Common Redistributables"), encoding="utf-8")
    (root / "steamapps" / "appmanifest_999.acf").write_text(acf("999", "Half Installed", flags="1026"), encoding="utf-8")
    return root


def epic_item(app: str, name: str, ns: str = "ns1", item: str = "item1", **extra) -> str:
    data = {"FormatVersion": 0, "bIsIncompleteInstall": False, "LaunchCommand": "", "LaunchExecutable": f"{app}/Binaries/Win64/{app}.exe",
            "ManifestLocation": "C:\\ProgramData/Epic/EpicGamesLauncher/Data/Manifests", "bIsApplication": True, "bIsExecutable": True,
            "bIsManaged": False, "bNeedsValidation": False, "bRequiresAuth": True, "bCanRunOffline": True, "AppName": app,
            "BaseURLs": [], "BuildLabel": "Live", "CatalogItemId": item, "CatalogNamespace": ns, "AppCategories": ["public", "games", "applications"],
            "ChunkDbs": [], "CompatibleApps": [], "DisplayName": name, "InstallationGuid": "ABC", "InstallLocation": f"C:\\Program Files\\Epic Games\\{name}",
            "InstallSessionId": "X", "InstallTags": [], "InstallComponents": [], "HostInstallationGuid": "0", "PrereqIds": [],
            "StagingLocation": "", "TechnicalType": "games", "VaultThumbnailUrl": "", "VaultTitleText": "", "InstallSize": 123,
            "MainWindowProcessName": "", "ProcessNames": [], "ExpectingDLCInstalled": {}, "MandatoryAppFolderName": name,
            "OwnershipToken": "false", "MainGameCatalogNamespace": ns, "MainGameCatalogItemId": item, "MainGameAppName": app,
            "AppVersionString": "1.0"}
    data.update(extra)
    return json.dumps(data, indent=4, ensure_ascii=False)


class SteamDetection(unittest.TestCase):
    def test_new_format_library_folders_and_manifests_across_drives(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_steam(Path(d))
            games = pcgames.steam_games({"STEAM_ROOT": str(root)})
            libs = pcgames.steam_libraries(root)
        self.assertEqual({"Portal 2", "Hades", "サイバーパンク2077 Ünïcødé"}, {g["title"] for g in games})
        self.assertEqual(2, len(libs))

    def test_old_format_library_folders(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_steam(Path(d), new_format=False)
            self.assertEqual(3, len(pcgames.steam_games({"STEAM_ROOT": str(root)})))

    def test_vdf_reader_handles_escapes_slashes_comments_and_conditions(self):
        data = pcgames.parse_vdf('// a comment\n"LibraryFolders"\n{\n "1" "D:\\\\Games\\\\Steam Library"\n "2" "E:/SteamLibrary"\n'
                                 ' "3" "F:\\Unescaped"\n "quote" "say \\"hi\\"" [$WIN32]\n "x" { "y" "z" }\n}\n')
        top = data["LibraryFolders"]
        self.assertEqual("D:\\Games\\Steam Library", top["1"])
        self.assertEqual("E:/SteamLibrary", top["2"])
        self.assertEqual("F:\\Unescaped", top["3"])
        self.assertEqual('say "hi"', top["quote"])
        self.assertEqual({"y": "z"}, top["x"])
        self.assertEqual("z", pcgames._ci(data, "libraryfolders", "X", "Y"))

    def test_registry_finds_steam_without_any_setting(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_steam(Path(d))
            values = {("HKCU", r"Software\Valve\Steam", "SteamPath"): str(root).replace("\\", "/")}
            with mock.patch.object(pcgames, "registry_value", side_effect=lambda h, k, n="": values.get((h, k, n))):
                info = pcgames.steam_install({})
                self.assertTrue(info["installed"])
                self.assertEqual("the registry", info["how"])
                self.assertEqual(3, len(pcgames.steam_games({})))

    def test_steam_exe_value_and_hklm_install_path(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_steam(Path(d))
            for values in ({("HKCU", r"Software\Valve\Steam", "SteamExe"): str(root / "steam.exe")},
                           {("HKLM", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"): str(root)}):
                with mock.patch.object(pcgames, "registry_value", side_effect=lambda h, k, n="", v=values: v.get((h, k, n))):
                    self.assertEqual(str(root), pcgames.steam_install({})["root"])

    def test_program_files_found_whatever_the_capitals(self):
        # On Windows dict(os.environ) spells it PROGRAMFILES(X86); the old reader asked for ProgramFiles(x86) and missed it.
        with tempfile.TemporaryDirectory() as d:
            make_steam(Path(d))
            self.assertTrue(pcgames.steam_install({"PROGRAMFILES(X86)": d})["installed"])

    def test_installed_without_games_is_still_installed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "Steam"
            root.mkdir()
            (root / "steam.exe").write_bytes(b"MZ")
            status = pcgames.store_status({"STEAM_ROOT": str(root)})
        self.assertTrue(status["steam"]["installed"])
        self.assertEqual(0, status["steam"]["games"])
        self.assertTrue(status["ready"])
        self.assertIn("Steam is installed: 0 games", status["text"])


class EpicDetection(unittest.TestCase):
    def test_items_launcher_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            pd = Path(d) / "ProgramData"
            man = pd / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
            man.mkdir(parents=True)
            (man / "A1.item").write_text(epic_item("Fortnite", "Fortnite", "fn", "4fe7"), encoding="utf-8")
            (man / "B2.item").write_text("\ufeff" + epic_item("Sugar", "Ōkami HD", "ns2", "it2"), encoding="utf-8")
            (man / "C3.item").write_text(epic_item("DlcPack", "Some DLC", "ns3", "it3", bIsApplication=False, MainGameAppName="Sugar"), encoding="utf-8")
            (man / "D4.item").write_text(epic_item("Half", "Half", bIsIncompleteInstall=True), encoding="utf-8")
            (man / "E5.item").write_text(epic_item("UE_5.3", "Unreal Engine", AppCategories=["engines"]), encoding="utf-8")
            (man / "F6.item").write_text("{not json", encoding="utf-8")
            env = {"PROGRAMDATA": str(pd)}
            games = pcgames.epic_games(env)
            status = pcgames.store_status(env)
        self.assertEqual({"Fortnite", "Ōkami HD"}, {g["title"] for g in games})
        self.assertTrue(status["epic"]["installed"])
        self.assertEqual("Epic is installed: 2 games.", status["text"])

    def test_launcher_from_registry_and_manifests_from_app_data_path(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "Epic Games" / "Launcher" / "Portal" / "Binaries" / "Win64" / "EpicGamesLauncher.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"MZ")
            data = Path(d) / "EpicData"
            (data / "Manifests").mkdir(parents=True)
            (data / "Manifests" / "x.item").write_text(epic_item("Hades", "Hades", "min", "abc"), encoding="utf-8")
            values = {("HKCR", r"com.epicgames.launcher\shell\open\command", ""): f'"{exe}" %1',
                      ("HKLM", r"SOFTWARE\WOW6432Node\Epic Games\EpicGamesLauncher", "AppDataPath"): str(data) + "/"}
            with mock.patch.object(pcgames, "registry_value", side_effect=lambda h, k, n="": values.get((h, k, n))):
                info = pcgames.epic_install({})
                games = pcgames.epic_games({})
                entries = pcgames.library_entries({})
        self.assertTrue(info["installed"])
        self.assertEqual(str(exe), info["exe"])
        self.assertEqual(["Hades"], [g["title"] for g in games])
        epic = next(e for e in entries if e["root"] == "epic")
        self.assertEqual(("min", "abc", "Hades"), (epic["epic_ns"], epic["epic_item"], epic["store_key"]))
        self.assertEqual({"store": "epic", "app": "Hades", "ns": "min", "item": "abc"}, pcgames.store_ids(epic))
        # an older library cache without the extra fields still yields the ids from the launch address
        old = {k: v for k, v in epic.items() if k not in ("epic_ns", "epic_item", "store_key")}
        self.assertEqual({"store": "epic", "app": "Hades", "ns": "min", "item": "abc"}, pcgames.store_ids(old))

    def test_nothing_installed_says_so(self):
        status = pcgames.store_status({"STEAM_ROOT": "/nowhere/at/all", "EPIC_MANIFESTS": "/nowhere/either"})
        self.assertFalse(status["ready"])
        self.assertIn("Neither Steam nor the Epic Games Launcher", status["text"])


def cloud_storage(hidden: list[int], removed: list[int] = (), deleted: bool = False) -> str:
    value = {"id": "hidden", "name": "", "added": hidden, "removed": list(removed)}
    fav = {"id": "favorite", "name": "", "added": [620], "removed": []}
    rows = [["user-collections.favorite", {"key": "user-collections.favorite", "timestamp": 1700000000, "value": json.dumps(fav),
                                           "version": "12", "conflictResolutionMethod": "custom", "strMethodId": "union-collections"}],
            ["user-collections.hidden", {"key": "user-collections.hidden", "timestamp": 1700000001, "value": json.dumps(value),
                                         "version": "13", "conflictResolutionMethod": "custom", "strMethodId": "union-collections",
                                         **({"is_deleted": True} if deleted else {})}],
            ["user-collections.uc-AbCdEf", {"key": "user-collections.uc-AbCdEf", "timestamp": 1700000002,
                                            "value": json.dumps({"id": "uc-AbCdEf", "name": "Co-op", "added": [730], "removed": []}), "version": "3"}],
            ["showcases.12345", {"key": "showcases.12345", "timestamp": 1, "value": "{}", "version": "1"}]]
    return json.dumps(rows)


class SteamHidden(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_steam(Path(self.tmp.name))
        self.env = {"STEAM_ROOT": str(self.root)}

    def tearDown(self):
        self.tmp.cleanup()

    def account(self, account_id: str) -> Path:
        base = self.root / "userdata" / account_id
        (base / "config" / "cloudstorage").mkdir(parents=True, exist_ok=True)
        (base / "7" / "remote").mkdir(parents=True, exist_ok=True)
        return base

    def test_collections_file_lists_hidden_games(self):
        base = self.account("12345")
        (base / "config" / "cloudstorage" / "cloud-storage-namespace-1.json").write_text(cloud_storage([1145360, 1091500], removed=[1091500]))
        self.assertEqual({"1145360"}, pcgames.steam_hidden(self.env))

    def test_deleted_hidden_collection_hides_nothing_and_beats_old_files(self):
        base = self.account("12345")
        (base / "config" / "cloudstorage" / "cloud-storage-namespace-1.json").write_text(cloud_storage([1145360], deleted=True))
        (base / "7" / "remote" / "sharedconfig.vdf").write_text('"UserRoamingConfigStore" { "Software" { "Valve" { "Steam" { "apps" { "620" { "Hidden" "1" } } } } } }')
        self.assertEqual(set(), pcgames.steam_hidden(self.env))

    def test_older_sharedconfig_and_localconfig(self):
        base = self.account("12345")
        (base / "7" / "remote" / "sharedconfig.vdf").write_text(
            '"UserRoamingConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"Apps"\n\t\t\t\t{\n'
            '\t\t\t\t\t"620"\n\t\t\t\t\t{\n\t\t\t\t\t\t"tags"\n\t\t\t\t\t\t{\n\t\t\t\t\t\t\t"0"\t\t"favorite"\n\t\t\t\t\t\t}\n\t\t\t\t\t\t"Hidden"\t\t"1"\n\t\t\t\t\t}\n'
            '\t\t\t\t\t"730"\n\t\t\t\t\t{\n\t\t\t\t\t\t"tags"\n\t\t\t\t\t\t{\n\t\t\t\t\t\t\t"0"\t\t"hidden"\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n'
            '\t\t\t\t\t"440"\n\t\t\t\t\t{\n\t\t\t\t\t\t"Hidden"\t\t"0"\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n')
        (base / "config" / "localconfig.vdf").write_text(
            '"UserLocalConfigStore"\n{\n "Software"\n {\n  "Valve"\n  {\n   "Steam"\n   {\n    "apps"\n    {\n     "1145360"\n     {\n'
            '      "LastPlayed"  "1700000000"\n      "Hidden"  "1"\n     }\n    }\n   }\n  }\n }\n}\n')
        self.assertEqual({"620", "730", "1145360"}, pcgames.steam_hidden(self.env))

    def test_most_recent_account_is_the_one_read(self):
        mine, other = self.account("12345"), self.account("67890")
        (mine / "config" / "cloudstorage" / "cloud-storage-namespace-1.json").write_text(cloud_storage([620]))
        (other / "config" / "cloudstorage" / "cloud-storage-namespace-1.json").write_text(cloud_storage([1145360]))
        (self.root / "config").mkdir(exist_ok=True)
        (self.root / "config" / "loginusers.vdf").write_text(
            '"users"\n{\n\t"%d"\n\t{\n\t\t"AccountName"\t\t"me"\n\t\t"MostRecent"\t\t"1"\n\t\t"Timestamp"\t\t"1700000000"\n\t}\n'
            '\t"%d"\n\t{\n\t\t"AccountName"\t\t"sibling"\n\t\t"MostRecent"\t\t"0"\n\t}\n}\n' % (pcgames.STEAM_ID64_BASE + 12345, pcgames.STEAM_ID64_BASE + 67890))
        self.assertEqual({"620"}, pcgames.steam_hidden(self.env))
        (self.root / "config" / "loginusers.vdf").unlink()            # cannot tell who: every account counts
        self.assertEqual({"620", "1145360"}, pcgames.steam_hidden(self.env))


ENTRIES = [
    {"id": "steam-620", "console": "pc", "title": "Portal 2", "sort_title": "portal 2", "region": "", "tags": ["Steam"], "path": "steam://rungameid/620",
     "root": "steam", "size": 1, "extension": ".steam", "is_archive": False, "compat_id": "pc:steam:portal-2"},
    {"id": "steam-730", "console": "pc", "title": "CS", "sort_title": "cs", "region": "", "tags": ["Steam"], "path": "steam://rungameid/730",
     "root": "steam", "size": 1, "extension": ".steam", "is_archive": False, "compat_id": "pc:steam:cs"},
]
STORES = {"steam": {"installed": True, "games": 23, "root": "C:\\Steam"}, "epic": {"installed": True, "games": 4}, "ready": True,
          "text": "Steam is installed: 23 games; Epic is installed: 4 games."}


class DoctorAndAdoption(unittest.TestCase):
    def setUp(self):
        self.app = LauncherApp(Path(tempfile.mkdtemp()))
        self.hidden = {"620", "730"}
        for p in (mock.patch("launcher.app.pcgames.library_entries", return_value=[dict(e) for e in ENTRIES]),
                  mock.patch("launcher.app.pcgames.steam_hidden", side_effect=lambda env=None: set(self.hidden)),
                  mock.patch("launcher.app.pcgames.steam_art", return_value=None),
                  mock.patch("launcher.app.pcgames.store_status", return_value=STORES)):
            p.start()
            self.addCleanup(p.stop)

    def test_doctor_counts_pc_ready_and_says_what_it_found(self):
        self.app.rescan()
        dr = self.app.api_doctor({})
        pc = next(c for c in dr["library"] if c["name"].startswith("PC games"))
        self.assertEqual("Steam and Epic Games Launcher", pc["emulator"])        # nothing is "still waiting" for PC games
        self.assertEqual("Steam is installed: 23 games; Epic is installed: 4 games.", dr["pc_stores"]["text"])
        self.assertTrue(dr["pc_stores"]["ready"])
        # the PC console counts as ready even with no emulator anywhere
        from launcher.consoles import CONSOLES
        others = sum(1 for c in CONSOLES if c.id != "pc" and self.app._emulator_for(c.id)[0])
        self.assertEqual(1 + others, dr["consoles_ready"])
        self.assertEqual(dr["consoles_ready"], self.app.api_home({})["consoles_ready"])
        self.assertNotIn("pc", [i["key"] for i in dr["issues"]])

    def test_doctor_without_launchers_is_honest(self):
        with mock.patch("launcher.app.pcgames.store_status", return_value={"steam": {"installed": False, "games": 0}, "epic": {"installed": False, "games": 0},
                                                                             "ready": False, "text": "Neither"}):
            self.app._stores_cache = None
            self.assertEqual(0, self.app.api_doctor({})["consoles_ready"])

    def test_last_computer_scan_is_recorded_and_told(self):
        self.assertEqual("never", self.app.api_doctor({})["last_scan_text"])
        when = time.time()
        self.app._record_scan(when)
        dr = self.app.api_doctor({})
        self.assertEqual(when, dr["last_scan"])
        self.assertEqual("today at " + time.strftime("%H:%M", time.localtime(when)), dr["last_scan_text"])
        self.assertTrue(self.app._when_text(when - 86400).startswith("yesterday at "))
        self.assertRegex(self.app._when_text(when - 40 * 86400), r"^\d{1,2} \w{3}( \d{4})? at \d\d:\d\d$")
        again = LauncherApp(self.app.data_dir)                        # kept in the catalog: survives a restart
        self.assertEqual(when, again.catalog.data["last_scan"])

    def test_scan_finishing_calls_back_with_the_time(self):
        seen = []
        s = pcscan.PcScan({}, on_done=seen.append)
        with mock.patch.object(pcscan, "standard_roots", return_value=[]), mock.patch.object(pcscan, "registry_locations", return_value=[]):
            s.start()
            s._thread.join(5)
        self.assertEqual("done", s.state)
        self.assertEqual([s.finished_at], seen)

    def test_hidden_in_steam_even_when_the_game_has_other_notes(self):
        # the old rule only hid a game that had no notes at all here; a note (or an earlier un-hide by Steam) blocked it forever
        self.app.catalog.set_game_meta("steam-620", note="great with friends")
        self.app.catalog.set_game_meta("steam-730", hidden=False, hidden_by="")
        self.app.rescan()
        metas = self.app.catalog.data["game_meta"]
        self.assertEqual((True, "steam"), (metas["steam-620"].get("hidden"), metas["steam-620"].get("hidden_by")))
        self.assertTrue(metas["steam-730"].get("hidden"))
        # the player shows one here: that wins over Steam from now on
        self.app.api_pc_games({"action": "hide", "ids": ["steam-620"], "hidden": False})
        self.app.rescan()
        self.assertFalse(self.app.catalog.data["game_meta"]["steam-620"].get("hidden"))
        # un-hidden in Steam: the one Steam had hidden comes back by itself
        self.hidden = set()
        self.app.rescan()
        self.assertFalse(self.app.catalog.data["game_meta"].get("steam-730", {}).get("hidden"))


if __name__ == "__main__":
    unittest.main()

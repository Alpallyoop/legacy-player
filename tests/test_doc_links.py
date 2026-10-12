"""Every relative link and #anchor in the repository's Markdown files points at something that exists
(tools/check_links.py), and the checker itself catches what it should."""
import tempfile
import unittest
from pathlib import Path

from tools import check_links

ROOT = Path(__file__).resolve().parent.parent


class RepositoryLinksTests(unittest.TestCase):
    def test_no_broken_relative_links_or_anchors(self):
        bad = check_links.check(ROOT)
        self.assertEqual([], [f"{f}:{n}: {t} ({why})" for f, n, t, why in bad])

    def test_the_main_documents_are_checked(self):
        names = {p.relative_to(ROOT).as_posix() for p in check_links.markdown_files(ROOT)}
        for rel in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "PRIVACY.md",
                    "docs/USER_GUIDE.md", "docs/RUNNING_LOCALLY.md", "docs/PROJECT_DOCUMENTATION_INDEX.md",
                    ".github/PULL_REQUEST_TEMPLATE.md", ".github/ISSUE_TEMPLATE/bug_report.md"):
            self.assertIn(rel, names)

    def test_the_index_lists_every_document(self):
        index = ROOT / "docs" / "PROJECT_DOCUMENTATION_INDEX.md"
        listed = {(index.parent / t.split("#")[0]).resolve() for _, t in check_links.links(index) if t.split("#")[0]}
        wanted = [p for p in check_links.markdown_files(ROOT)
                  if p != index and (p.parent == ROOT or ROOT / "docs" in p.parents)]
        self.assertEqual([], [p.relative_to(ROOT).as_posix() for p in wanted if p.resolve() not in listed])


class CheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "docs").mkdir()
        (self.root / "docs" / "B.md").write_text(
            "# Hello, World!\n\n## Step 1: set up\n\n## Step 1: set up\n\nOther title\n---\n\n<a name=\"custom\"></a>\n",
            encoding="utf-8")
        (self.root / "code.py").write_text("x = 1\n", encoding="utf-8")

    def broken(self, text):
        (self.root / "A.md").write_text(text, encoding="utf-8")
        check_links._ANCHORS.clear()
        return [(t, why) for f, n, t, why in check_links.check(self.root) if f == "A.md"]

    def test_good_links_pass(self):
        self.assertEqual([], self.broken(
            "[b](docs/B.md) [h](docs/B.md#hello-world) [s](docs/B.md#step-1-set-up) [s2](docs/B.md#step-1-set-up-1)\n"
            "[o](docs/B.md#other-title) [c](docs/B.md#custom) [code](code.py#L1) [dir](docs/) [root](/docs/B.md)\n"
            "[web](https://example.com/nothing) [mail](mailto:a@b.c) [self](#top)\n\n# Top\n"
            "[t](<docs/B.md> \"title\") ![img](docs/B.md)\n\n[ref]: docs/B.md\n"))

    def test_missing_file_and_anchor_are_caught(self):
        out = self.broken("[x](docs/C.md) [y](docs/B.md#nope) [z](#missing)\n[r]: nowhere.md\n<a href=\"gone.md\">g</a>\n")
        self.assertEqual(["docs/C.md", "docs/B.md#nope", "#missing", "nowhere.md", "gone.md"], [t for t, _ in out])

    def test_code_is_not_a_link(self):
        self.assertEqual([], self.broken("`[x](nowhere.md)`\n\n```\n[y](nowhere.md)\n```\n\n~~~md\n[z](gone.md)\n~~~\n"))

    def test_outside_the_repository_is_broken(self):
        out = self.broken("[x](../../etc/passwd)\n")
        self.assertEqual(1, len(out))

    def test_command_line_exit_code(self):
        (self.root / "A.md").write_text("[x](nowhere.md)\n", encoding="utf-8")
        check_links._ANCHORS.clear()
        self.assertEqual(1, check_links.main(["--root", str(self.root), "--quiet"]))
        (self.root / "A.md").write_text("[x](docs/B.md)\n", encoding="utf-8")
        self.assertEqual(0, check_links.main(["--root", str(self.root), "--quiet"]))


if __name__ == "__main__":
    unittest.main()

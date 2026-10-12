"""Check every relative link in the repository's Markdown files.

    python tools/check_links.py            # prints each broken link, exits 1 if there is one
    python tools/check_links.py --quiet    # only the summary line

What is checked, in every *.md file of the repository (the root, docs/, .github/, and every other folder; build output,
data folders and .git are skipped):

- inline links and images: [text](target), ![alt](target), with an optional "title";
- reference definitions: [label]: target;
- HTML links in Markdown: <a href="target">, <img src="target">.

A target is broken when it is a relative path (to the file's own folder, or to the repository root when it starts with
/) that does not exist, or when it carries a #anchor that matches no heading in the target Markdown file (GitHub's
heading anchors: lower case, punctuation dropped, spaces to hyphens, -1/-2 for repeats; explicit <a name="..."> or
id="..." anchors count too). Web links (http, https, mailto and the like) are not fetched. Links inside code blocks and
inline code are ignored, since they are examples, not links.

Standard library only; tests/test_doc_links.py runs it."""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", "node_modules", "dist", "build", "out", "data", "LegacyPlayerData", "artifacts", "__pycache__",
             ".venv", "venv", "env", "social", "smoke", "smoke-data", "_to_delete", "tmp", "temp", ".claude"}

FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
INLINE_CODE = re.compile(r"(`+)(?:(?!\1).)+?\1")
# [text](target "title") and ![alt](target); the text may hold one level of brackets
INLINE_LINK = re.compile(r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(\s*(<[^>]*>|[^\s()]+(?:\([^\s()]*\)[^\s()]*)*)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
REF_DEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)")
HTML_LINK = re.compile(r"<(?:a|img)\b[^>]*?\b(?:href|src)\s*=\s*[\"']([^\"']+)[\"']", re.I)
HTML_ANCHOR = re.compile(r"<[a-z][^>]*?\b(?:name|id)\s*=\s*[\"']([^\"']+)[\"']", re.I)
HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
SETEXT = re.compile(r"^\s{0,3}(=+|-+)\s*$")
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)


def markdown_files(root: Path = ROOT) -> list[Path]:
    out = []
    stack = [root]
    while stack:
        folder = stack.pop()
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in SKIP_DIRS and not p.is_symlink():
                    stack.append(p)
            elif p.suffix.lower() == ".md":
                out.append(p)
    return sorted(out)


def prose_lines(text: str):
    """(line number, line) for each line outside fenced code blocks, with inline code blanked out."""
    fence = None
    for n, line in enumerate(text.splitlines(), 1):
        m = FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            continue
        if m:
            fence = m.group(1)
            continue
        yield n, INLINE_CODE.sub(lambda c: " " * len(c.group(0)), line)


def slug(heading: str) -> str:
    """GitHub's anchor for a heading."""
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", heading)          # images: their alt text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)               # links: their text
    text = re.sub(r"<[^>]+>", "", text)                                # inline HTML
    text = text.replace("`", "")
    text = unicodedata.normalize("NFC", text).strip().lower()
    out = []
    for ch in text:
        if ch in (" ", "-", "_") or ch.isalnum():
            out.append("-" if ch == " " else ch)
        elif unicodedata.category(ch).startswith(("L", "N", "M")):
            out.append(ch)
    return "".join(out)


_ANCHORS: dict[Path, set[str]] = {}


def anchors(path: Path) -> set[str]:
    """Every anchor a Markdown file offers: its headings (GitHub style, with -1, -2 for repeats) and HTML name/id."""
    if path in _ANCHORS:
        return _ANCHORS[path]
    found: set[str] = set()
    seen: dict[str, int] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    lines = list(prose_lines(text))
    raw = text.splitlines()

    def add(title: str) -> None:
        base = slug(title)
        k = seen.get(base, 0)
        found.add(base if k == 0 else f"{base}-{k}")
        seen[base] = k + 1

    prev_n, prev_line = None, ""
    for n, line in lines:
        m = HEADING.match(raw[n - 1])
        if m:
            add(m.group(2))
        elif SETEXT.match(line) and prev_n == n - 1 and prev_line.strip() and not prev_line.lstrip().startswith(("|", "-", "*", ">")):
            add(prev_line.strip())
        for a in HTML_ANCHOR.findall(line):
            found.add(a)
        prev_n, prev_line = n, line
    _ANCHORS[path] = found
    return found


def links(path: Path):
    """(line number, target) for every link in the file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    for n, line in prose_lines(text):
        for m in INLINE_LINK.finditer(line):
            yield n, m.group(1)
        m = REF_DEF.match(line)
        if m:
            yield n, m.group(1)
        for target in HTML_LINK.findall(line):
            yield n, target


def problem(path: Path, target: str, root: Path = ROOT) -> str | None:
    """Why this link is broken, or None when it is fine (or not ours to check)."""
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    if not target or SCHEME.match(target) or target.startswith("//"):
        return None
    ref, _, anchor = target.partition("#")
    ref = unquote(ref.split("?", 1)[0])
    if ref:
        dest = (root / ref.lstrip("/")) if ref.startswith("/") else (path.parent / ref)
        try:
            dest = dest.resolve()
        except OSError:
            return "the path can not be read"
        if not dest.exists():
            return "no such file"
        try:
            dest.relative_to(root.resolve())
        except ValueError:
            return "points outside the repository"
    else:
        dest = path
    if anchor:
        if dest.is_dir() or dest.suffix.lower() != ".md":
            return None                                    # anchors into code or folders are GitHub's business
        anchor = unquote(anchor)
        if anchor.lower() not in {a.lower() for a in anchors(dest)} and not re.fullmatch(r"L\d+(-L\d+)?", anchor):
            return f"no heading #{anchor} in {dest.relative_to(root.resolve()).as_posix()}"
    return None


def check(root: Path = ROOT) -> list[tuple[str, int, str, str]]:
    """Every broken link: (file, line, target, why)."""
    root = Path(root).resolve()
    bad = []
    for path in markdown_files(root):
        for n, target in links(path):
            why = problem(path, target, root)
            if why:
                bad.append((path.relative_to(root).as_posix(), n, target, why))
    return bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check relative links and #anchors in the repository's Markdown files")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    bad = check(args.root)
    if not args.quiet:
        for f, n, target, why in bad:
            print(f"{f}:{n}: {target}  ({why})")
    files = len(markdown_files(args.root.resolve()))
    print(f"{len(bad)} broken link(s) in {files} Markdown files" if bad else f"All links fine in {files} Markdown files")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

# Legacy Player Tools

## Purpose

The tools layer contains helper utilities that support development, debugging, replay inspection, and pack authoring for Legacy Player.

These tools are not the runtime itself, but they are important for making the system observable, maintainable, and scalable.

---

## Checks used by contributors and CI

- `check_links.py`: every relative link and `#anchor` in the repository's Markdown files must point at something that
  exists (`python tools/check_links.py`; run by `tests/test_doc_links.py` and the docs-check workflow).
- `check_ui_syntax.js`: compiles every `<script>` block of `launcher/ui/index.html` without running it, because the
  page's Content-Security-Policy forbids eval and a syntax error would only show when the app opens
  (`node tools/check_ui_syntax.js`).
- `contrast_check.py`: measures text contrast in a running copy of the app (needs Playwright).
- `release_check.py`: what the release workflow runs before it builds (compile, all tests, repository check).
- `validate_repository.py`: JSON files parse, no empty Markdown, the Mario Party 4 profile exists.

See [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Intended areas

### `memory_probe/`

Tools for observing and validating emulator-visible state and memory regions during supported target investigation.

### `replay_inspector/`

Tools for viewing replay metadata, session markers, state hashes, and diagnostic events produced by Legacy Player sessions.

### `pack_builder/`

Tools for creating, validating, and refining game pack structures as support expands.

---

## Why this matters

Legacy Player will only scale if it can inspect and explain its own behavior.

These tools exist to support:

- reverse-engineering discipline
- structured investigation
- replay usefulness
- desync debugging
- maintainable game pack growth

---

## First implementation role

At the beginning, these tools can remain simple.

The first goal is to support:

- target investigation
- structured observation
- replay visibility
- pack authoring discipline

That is enough to help the first adapter and first game pack become real.

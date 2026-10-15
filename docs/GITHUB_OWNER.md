# GitHub owner name

This repository does not decide the GitHub account name it lives under. Constellation does.

- **Source of truth:** `registry/owner.json` in the Constellation repository. Nothing else is authoritative.
- **Where the name can appear here:** the `origin` git remote, links such as `github.com/<owner>/...` in README and docs, and release or download URLs.
- **Where it should not appear:** build scripts, code and configuration. If you need the owner in code, read it from the registry or from `git remote get-url origin`; do not type it.
- **Brand text is separate.** Publisher and company strings in installers or app metadata are a product decision, not the GitHub account name, and a rename does not change them.

## If the GitHub account is renamed

1. Rename the account on GitHub first.
2. From the Constellation repository run `scripts\set_owner.ps1 -NewOwner <name>` (dry run), review it, then run it again with `-Apply`. It updates `registry/owner.json`, every repository's `origin`, and `github.com/<old>/` links in tracked text files. It never commits and never rewrites history.
3. Review and commit the link changes in this repository.
4. Run `UPDATE_SITE.cmd` in Constellation, then the doctor.

Old links keep redirecting only while nobody else takes the old name. Receipts, signed files and hashes that contain the old name stay as written; they are records and are not edited.

Governed by Constellation: `docs/proposals/0008-oversight-plane-and-global-workbench-console.md`.

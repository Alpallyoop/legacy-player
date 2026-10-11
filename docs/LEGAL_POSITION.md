# Legacy Player Legal Position

## Purpose

Legacy Player is an interoperability and multiplayer infrastructure project for legacy games.

It is intended to provide tooling for session orchestration, emulator integration, replay logging, and self-hosted multiplayer support.

It is not a game distribution project.

---

## Legacy Player does not provide

Legacy Player does not provide:

- ROMs
- ISOs
- proprietary game assets
- copyrighted music, art, or code
- unauthorized copies of commercial games

Users are responsible for supplying their own legally obtained game data and emulator environments.

---

## Interoperability focus

Legacy Player is designed around interoperability and user-operated infrastructure.

Its functions include:

- session management
- state and compatibility validation
- replay and diagnostics
- runtime orchestration
- self-host multiplayer services

These functions are intended to support lawful personal use, research, preservation-adjacent tooling, and community infrastructure.

---

## No IP ownership claim

Legacy Player does not claim ownership over third-party game intellectual property.

Game names may be referenced for compatibility and descriptive support purposes only.

---

## Runtime assistance boundary

Legacy Player may include runtime assistance and orchestration behaviors needed to support online play, but the project should avoid distributing proprietary game code or bundled modifications derived from copyrighted binaries.

Project design should prefer:

- user-supplied environments
- interoperability tooling
- runtime coordination
- clean separation from game content distribution

---

## Operator responsibility

Users and server operators are responsible for ensuring that their use of Legacy Player complies with applicable law and the terms of the environments they operate.

---

## Public project posture

Public messaging for Legacy Player should remain clear:

- interoperability tool
- self-host infrastructure
- no bundled game content
- no proprietary asset distribution
- no claim of ownership over supported game IP

---

## Strategic note

The safest and strongest posture is to keep Legacy Player focused on infrastructure, orchestration, and compatibility rather than content distribution.

---

## Note (non-canonical): game identification from DAT files

This section explains an implementation choice; it does not change the position above.

Legacy Player can name a player's games exactly (canonical title, region, languages, revision, and whether the dump is
listed as verified) using No-Intro or Redump game lists, commonly called DAT files. The design keeps Legacy Player out of
content and list distribution entirely:

- **User-supplied lists only.** Legacy Player never bundles, mirrors or downloads a DAT file. The player picks lists they
  obtained themselves (Setup > Game lists), and only the file path is remembered.
- **Local hashing of the player's own files.** When the player presses "Match my games", Legacy Player reads the player's
  own game files on their computer to compute CRC32 and SHA-1 checksums, and compares them with the chosen lists. Nothing
  is uploaded, shared or sent anywhere; checksums are cached locally (by path, size and modification time).
- **Nothing distributed.** No games, BIOS files, DAT files or checksum databases are included with Legacy Player or
  fetched by it. The result is metadata about files the player already has.
- **Untrusted input handled defensively.** DAT files are parsed with the Python standard library; XML entity declarations
  and inline document type definitions are refused, so a crafted file cannot expand entities or reach outside the file.

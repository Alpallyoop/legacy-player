"""Version and where updates are announced. Checking only happens when the user presses the button."""
VERSION = "0.7.48"
REPO = "Alpallyoop/legacy-player"
# Where opt-in problem reports are sent (an https address that runs server/report_receiver.py). Empty until it is set
# up: reports then stay on the player's computer. A player can also set their own under Settings.
REPORT_URL = ""
# The built-in meeting point (server/rendezvous.py): a rented server that carries friends to a player's own server without
# either side seeing the other's address. Used only after the player allows "Meeting point for friends outside my home"
# (Permissions); a player can set another under Settings. Run by the maintainers on AWS Lightsail (us-east-1) since
# 2026-11-01; its certificate is pinned by this code (docs/HOSTING_PUBLIC_SERVER.md, docs/canonical/CURRENT_STATE.md).
PUBLIC_SERVER_CODE = "LP2-0068-CM2R-WH3T-FKHH-T89M-3379-YSSQ-WYM"
# Public keys (64 hex characters each) whose Ed25519 signature an update must carry. Empty: updates are checked only
# against the SHA-256 published with them, which proves they arrived intact but not who published them. Once a key is
# listed, an update without a valid <zip>.sig from one of these keys is refused. Make one with
# `python tools/sign_release.py new-key` (docs/RELEASE.md, "Update signing"). Keep two here while changing keys.
UPDATE_SIGNING_KEYS: tuple[str, ...] = (
    "c2109f91534e579f19a5e79e8df20192acf92046f423e9ffccfc6724ff371054",     # made by the maintainer 2026-11-04
)

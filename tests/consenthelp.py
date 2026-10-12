"""Tests that exercise a feature behind a permission say yes to it the way the player does: through the permission
dialog's endpoint (api_consent), never by flipping a setting (that alone is not consent)."""


def allow(app, *items):
    for item in items:
        app.api_consent({"action": "decide", "item": item, "decision": "allow"})
    return app

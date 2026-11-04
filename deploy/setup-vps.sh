#!/usr/bin/env bash
# One-step setup of a Legacy Player shared server on a fresh Ubuntu/Debian machine with a public address.
#   curl -fsSL https://raw.githubusercontent.com/Alpallyoop/legacy-player/main/deploy/setup-vps.sh | sudo bash
# It installs Python and git, downloads the server, starts it (and keeps it running after a reboot), opens TCP 8765 in the
# machine's own firewall and prints the server code to give your players. Open TCP 8765 in your provider's cloud firewall too.
# Run it again any time to update; the code stays the same. Set LP_ADDRESS=name.or.ip first to use a name instead of the detected address.
# It installs the newest release tag (vX.Y.Z), not whatever is on main; set LP_REF=v0.7.50 (a tag) or LP_REF=main to choose.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run this with sudo."; exit 1; }
PORT="${LP_PORT:-8765}"
[[ "$PORT" =~ ^[0-9]{1,5}$ ]] && [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || { echo "LP_PORT must be a port number."; exit 1; }
REPO_URL="https://github.com/Alpallyoop/legacy-player"
DEST=/opt/legacy-player
apt-get update -y >/dev/null
apt-get install -y python3 git curl >/dev/null
id legacyplayer >/dev/null 2>&1 || useradd --system --home /var/lib/legacy-player --shell /usr/sbin/nologin legacyplayer
mkdir -p /var/lib/legacy-player/state /var/lib/legacy-player/replays
REF="${LP_REF:-}"
if [ -z "$REF" ]; then          # the newest plain release tag (vX.Y.Z); main only if the repository has none
  REF="$(git ls-remote --tags --refs "$REPO_URL" 'v*' | sed 's#.*refs/tags/##' | grep -E '^v[0-9]+(\.[0-9]+)*$' | sort -V | tail -n 1 || true)"
  [ -n "$REF" ] || { REF=main; echo "No release tag found; installing main."; }
fi
[[ "$REF" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]] || { echo "LP_REF is not a tag or branch name: $REF"; exit 1; }
echo "Installing Legacy Player $REF"
if [ ! -d "$DEST/.git" ]; then
  mkdir -p "$DEST"
  git -C "$DEST" init -q
  git -C "$DEST" remote add origin "$REPO_URL"
fi
git -C "$DEST" fetch -q --depth 1 origin "$REF"
git -C "$DEST" checkout -q --detach FETCH_HEAD        # refuses (and stops here) if someone changed files in $DEST by hand
chown -R legacyplayer: /var/lib/legacy-player
sed "s/--port 8765/--port ${PORT}/" "$DEST/deploy/legacy-player-server.service" > /etc/systemd/system/legacy-player-server.service
DROPIN=/etc/systemd/system/legacy-player-server.service.d
if [ "$PORT" -lt 1024 ]; then   # the unit grants no capabilities; a port below 1024 needs exactly this one
  mkdir -p "$DROPIN"
  printf '[Service]\nCapabilityBoundingSet=CAP_NET_BIND_SERVICE\nAmbientCapabilities=CAP_NET_BIND_SERVICE\n' > "$DROPIN/low-port.conf"
else
  rm -f "$DROPIN/low-port.conf"
fi
systemctl daemon-reload
systemctl enable legacy-player-server >/dev/null
systemctl restart legacy-player-server
if command -v ufw >/dev/null 2>&1; then ufw allow "${PORT}/tcp" >/dev/null || true; fi
ADDRESS="${LP_ADDRESS:-$(curl -fsS -4 https://api.ipify.org || true)}"
[ -n "$ADDRESS" ] || { echo "Could not find this machine's public address. Run again with LP_ADDRESS=your.address"; exit 1; }
sleep 2
echo
echo "Server is running. Give this code to your players (Settings > Your server > Shared server code):"
cd "$DEST"
sudo -u legacyplayer python3 -m server.cli code --state-dir /var/lib/legacy-player/state --address "$ADDRESS" --port "$PORT"
echo
echo "If friends cannot connect, open TCP ${PORT} in your provider's firewall / security group."

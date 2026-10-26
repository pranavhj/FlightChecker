#!/usr/bin/env bash
# Install / update flightchecker on the Raspberry Pi (Debian, aarch64). Idempotent: safe to rerun.
# Run on the Pi:  bash ~/flightchecker/deploy/install_pi.sh
set -euo pipefail
ROOT="$HOME/flightchecker"
cd "$ROOT"

sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv chromium

[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
# No `playwright install`: Playwright has no browser build for Debian arm64; settings.yaml points at /usr/bin/chromium

mkdir -p logs && chmod 755 logs   # not group-writable, or logrotate skips the logs

sudo cp deploy/flightchecker.service deploy/flightchecker.timer /etc/systemd/system/
sudo cp deploy/logrotate.conf /etc/logrotate.d/flightchecker
sudo systemctl daemon-reload
sudo systemctl enable --now flightchecker.timer
systemctl list-timers flightchecker.timer --no-pager
echo "Installed. Run now: sudo systemctl start --no-block flightchecker.service; log: ~/flightchecker/logs/flightchecker.log"

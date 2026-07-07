#!/usr/bin/env bash
# Install the dark factory as a 24/7 launchd service on macOS.
# launchd restarts it if it crashes and starts it at login — that, plus
# SQLite-persisted schedule state, is what makes the loop truly 24/7 on a
# MacBook Air. (Close the lid? See caffeinate note at the bottom.)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_LABEL="com.darkfactory.harness"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
PYTHON_BIN="${PYTHON_BIN:-$REPO_DIR/.venv/bin/python}"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Creating venv and installing darkfactory…"
  python3 -m venv "$REPO_DIR/.venv"
  "$REPO_DIR/.venv/bin/pip" install -q -e "$REPO_DIR"
fi

mkdir -p "$REPO_DIR/workspace/logs" "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$PLIST_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>-m</string>
    <string>darkfactory</string>
    <string>run</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$REPO_DIR/workspace/logs/darkfactory.log</string>
  <key>StandardErrorPath</key><string>$REPO_DIR/workspace/logs/darkfactory.err</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key><string>http://localhost:11434</string>
  </dict>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "Installed and started: $PLIST_LABEL"
echo "  logs:   tail -f $REPO_DIR/workspace/logs/darkfactory.log"
echo "  status: $PYTHON_BIN -m darkfactory status"
echo "  stop:   launchctl unload $PLIST_PATH"
echo
echo "NOTE: a MacBook Air sleeps when the lid closes. For true 24/7 either:"
echo "  - keep it on power + lid open with 'caffeinate -s' running, or"
echo "  - System Settings → prevent sleep on power adapter, or"
echo "  - accept that the factory catches up when the Mac wakes (the scheduler"
echo "    is persistent, so nothing is lost — runs just happen later)."

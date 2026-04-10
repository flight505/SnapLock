#!/bin/bash
# deploy.sh — Helper for registering SnapLock in Fusion 360.
#
# SnapLock is loaded directly from this Projects folder — no symlink or copy
# in ~/Library/.../API/AddIns/ is needed. Register once via Shift+S → + button
# and Fusion will pick up edits automatically on reload.
#
# This script exists only to print installation instructions.

cat <<'EOF'
SnapLock does not use a deploy step.

To install (first time only):
  1. Open Fusion 360
  2. Shift+S → Scripts and Add-Ins
  3. Click the "+" button
  4. Navigate to /Users/jesper/Projects/3Dprint/SnapLock
  5. Select the folder and click Open

After that, just edit the source in this folder. Toggle Run off/on in the
Scripts and Add-Ins dialog to reload after changes.
EOF

#!/bin/bash
# deploy.sh — Symlink SnapLock add-in into Fusion 360's AddIns directory.
#
# Uses a symlink (not a copy) so edits in this repo are reflected immediately
# after reloading the add-in in Fusion. The source directory has a trailing
# space in its name (historical), which we normalize away in the destination.

set -e

SRC="/Users/jesper/Projects/3Dprint/SnapLock "
DST="/Users/jesper/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/SnapLock"

echo "Deploying SnapLock → $DST"

# Remove any existing entry (whether it's a symlink, file, or directory)
if [ -e "$DST" ] || [ -L "$DST" ]; then
    rm -rf "$DST"
    echo "  ✓ removed previous install"
fi

mkdir -p "$(dirname "$DST")"
ln -s "$SRC" "$DST"
echo "  ✓ symlinked $SRC → $DST"

# Fusion looks for a manifest file with the same basename as the folder.
# Source manifest is "SnapLock .manifest" (trailing space). Fusion won't find
# it inside the symlinked "SnapLock" folder because the manifest basename
# doesn't match the folder basename. Create a clean manifest alongside the
# source if needed.
SRC_MANIFEST="$SRC/SnapLock .manifest"
CLEAN_MANIFEST="$SRC/SnapLock.manifest"
if [ -f "$SRC_MANIFEST" ] && [ ! -e "$CLEAN_MANIFEST" ]; then
    cp "$SRC_MANIFEST" "$CLEAN_MANIFEST"
    echo "  ✓ created SnapLock.manifest (clean copy)"
fi

SRC_PY="$SRC/SnapLock .py"
CLEAN_PY="$SRC/SnapLock.py"
if [ -f "$SRC_PY" ] && [ ! -e "$CLEAN_PY" ]; then
    cp "$SRC_PY" "$CLEAN_PY"
    echo "  ✓ created SnapLock.py (clean copy)"
fi

echo ""
echo "Done. In Fusion 360:"
echo "  1. Shift+S → Add-Ins tab"
echo "  2. SnapLock should appear in the list"
echo "  3. Select it → Run (or toggle 'Run on Startup')"
echo "  4. In Solid workspace, the '3D Print Tools' panel gets a 'SnapLock' button"

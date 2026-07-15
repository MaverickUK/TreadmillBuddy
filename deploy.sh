#!/usr/bin/env bash
# =============================================================================
# Copy Treadmill Buddy's CircuitPython code to the Pico's CIRCUITPY drive.
# -----------------------------------------------------------------------------
# Usage:
#   ./deploy.sh              copy all .py files + lib/ to CIRCUITPY
#   ./deploy.sh --delete     also remove files on CIRCUITPY that aren't in
#                            this repo (careful: wipes anything else you've
#                            put on the drive, e.g. boot_out.txt is kept)
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOLUME="/Volumes/CIRCUITPY"

if [ ! -d "$VOLUME" ]; then
    echo "error: $VOLUME not found - is the Pico plugged in and running CircuitPython?" >&2
    exit 1
fi

RSYNC_FLAGS=(-av --exclude ".DS_Store" --exclude "__pycache__/" --exclude "*.pyc")
if [[ "${1:-}" == "--delete" ]]; then
    RSYNC_FLAGS+=(--delete --exclude "boot_out.txt")
fi

echo "Copying .py files to $VOLUME ..."
rsync "${RSYNC_FLAGS[@]}" --include="*.py" --exclude="*" "$REPO_DIR"/ "$VOLUME"/

echo "Copying lib/ to $VOLUME/lib ..."
rsync "${RSYNC_FLAGS[@]}" "$REPO_DIR/lib/" "$VOLUME/lib/"

echo "Done."

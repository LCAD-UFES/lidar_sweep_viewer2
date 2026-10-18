#!/bin/sh
# Builds a self-contained lsv2 executable for THIS platform (python, libraries and ffmpeg inside).
# Run inside the lsv2 conda environment; pyinstaller is an optional row of the manifest.
# Output: <workdir>/dist/lsv2. Credentials are still supplied by the user (gcloud is not bundled).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${1:-"$HERE/../build"}
FFMPEG=$(command -v ffmpeg) || { echo "ffmpeg not on PATH" >&2; exit 1; }
mkdir -p "$WORK" && cd "$WORK"
pyinstaller --onefile --name lsv2 --clean --noconfirm \
    --paths "$HERE/.." \
    --add-binary "$FFMPEG:." \
    --collect-all pyarrow --collect-all av --collect-all google \
    --hidden-import lsv2.source.gcs \
    "$HERE/entry.py"
echo "built $WORK/dist/lsv2 ($(du -h "$WORK/dist/lsv2" | cut -f1))"

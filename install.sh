#!/usr/bin/env bash
# Installs Video Tweaks for the current user. Run again to update, or with --uninstall to remove.
set -euo pipefail
cd "$(dirname "$0")"
BIN="$HOME/.local/bin"
EXT="$HOME/.local/share/nautilus-python/extensions"

if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$BIN/video-tweaks" "$BIN/dcomp" "$EXT/video_tweaks.py"
  echo "Removed. Restart Files with: nautilus -q"
  exit 0
fi

missing=0
for c in ffmpeg ffprobe; do
  command -v "$c" >/dev/null || { echo "Missing: $c"; missing=1; }
done
[[ "$(ffmpeg -hide_banner -encoders 2>/dev/null)" == *libx264* ]] || { echo "Missing: ffmpeg with libx264"; missing=1; }
/usr/bin/python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")' 2>/dev/null \
  || { echo "Missing: Python GTK 4 / libadwaita bindings"; missing=1; }
compgen -G "/usr/lib*/nautilus/extensions-4/libnautilus-python.so" >/dev/null \
  || compgen -G "/usr/lib/*/nautilus/extensions-4/libnautilus-python.so" >/dev/null \
  || { echo "Missing: nautilus-python (needed for the right-click item)"; missing=1; }
[ "$missing" = 0 ] || { echo "Install the missing packages (see README.md), then run this again."; exit 1; }

install -Dm755 -t "$BIN" video-tweaks dcomp
install -Dm644 -t "$EXT" nautilus/video_tweaks.py
echo "Installed. Restart Files with: nautilus -q"

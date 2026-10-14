#!/bin/sh
# Copy the add-on into the Flatpak Kodi's addons folder (what install-local points at).
# Restart Kodi (or run UpdateLocalAddons) and enable "Center Stage" under My add-ons.
set -e
cd "$(dirname "$0")/.."
DEST="${KODI_ADDONS:-$HOME/.var/app/tv.kodi.Kodi/data/addons}/script.centerstage"
mkdir -p "$DEST"
rsync -a --delete --exclude '__pycache__' \
    addon.xml default.py plugin.py context.py LICENSE resources "$DEST/"
[ -e install-local ] || ln -s "$DEST/" install-local
echo "installed to $DEST"

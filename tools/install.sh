#!/bin/sh
# Copy the add-on into a local Kodi's addons folder: $KODI_ADDONS, else the Flatpak Kodi's if it
# exists, else ~/.kodi/addons. install-local links to the copy.
# Restart Kodi (or run UpdateLocalAddons) and enable "Center Stage" under My add-ons.
set -e
cd "$(dirname "$0")/.."
if [ -z "$KODI_ADDONS" ]; then
    KODI_ADDONS="$HOME/.var/app/tv.kodi.Kodi/data/addons"
    [ -d "$KODI_ADDONS" ] || KODI_ADDONS="$HOME/.kodi/addons"
fi
DEST="$KODI_ADDONS/script.centerstage"
mkdir -p "$DEST"
rsync -a --delete --exclude '__pycache__' \
    addon.xml default.py plugin.py context.py LICENSE resources "$DEST/"
[ -e install-local ] || ln -s "$DEST/" install-local
echo "installed to $DEST"

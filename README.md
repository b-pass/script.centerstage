# Center Stage (`script.centerstage`)

This Kodi 21/22 add-on shows one list of everything you watch: DVR recordings, library shows,
seasons and movies, and shows or videos from other add-ons.

- **Left:** every title, from all sources, in one list.
- **Top right:** the selected title's episodes, or its seasons and other folders (Extras, Next
  page, …). Select an episode to play it, or a folder to open it in place. A ".." row or **Back**
  goes up a level, and **left** always returns to the titles, keeping your place. A movie or
  single video shows as one row.
- **Bottom right:** artwork and description of whatever is focused. For a title, this pane also
  shows where it comes from.

DVR recordings appear automatically, one row per recording title. Everything else you add with
**Center Stage…** in the context menu, which appears on library items, recordings, add-on listings,
Favourites and home-screen widgets. If you add a season folder from another add-on, it's named
"Show - Season N". When the add-on doesn't provide the show name, you're asked for it.

## Using it

- Open it from **Programs** or **Video add-ons**.
- **Recording groups:** if your DVR files recordings in groups (MythTV recording groups), you're
  first asked which group to show, or "All groups". When you add something with the context menu,
  you pick the group it belongs to, or all of them.
- In the window:
  - **Left/right** moves between titles and episodes.
  - **Back** returns to the titles, then to the group question (or closes the window).
  - **Context menu** on a title: Rename, Refresh, Remove (or Hide, for a DVR series), "Recording
    group…" for titles you added, "Show hidden DVR series…" and "Switch recording group…".
- **Widget:** point a skin widget at `plugin://script.centerstage/?action=list`, or
  `?action=list&group=Emily` for one recording group. Clicking a title opens the window on it.
- **Settings:** title sort order (A-Z or recently added), episode order, hide watched episodes,
  include DVR recordings, ask for a recording group when opening, and how long add-on listings
  are cached.

## Limits

These come from Kodi itself; see `CLAUDE.md` for the source references.

- Other add-ons are run in the background to list their folders. If an add-on changes its URLs,
  puts session tokens in them, or needs its own menus to have been visited first, its saved
  entries can break. An add-on may also pop up its own login or error dialogs.
- On **Kodi 21**, add-on episodes only show watched and resume state if that add-on sets it
  itself. On **Kodi 22**, Kodi's own watched and resume state is used.
- On Estuary, the window uses Estuary's own background, colours, fonts and list style. Other
  skins get a neutral dark layout that only roughly matches them.
- The context menu isn't available during playback or inside other add-ons' custom windows.

## Development

```
python3 -m unittest discover tests     # Kodi-free logic: classify, store, sources, catalog
tools/install.sh                       # copy into the Flatpak Kodi's addons folder
```

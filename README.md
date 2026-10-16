<img src="resources/icon.png" alt="Center Stage icon" width="128" align="right">

# Center Stage (`script.centerstage`)

This Kodi 21/22 add-on shows one list of everything you watch: DVR recordings, library shows,
seasons and movies, and shows or videos from other add-ons.

- **Left:** every title, from all sources, in one list.
- **Top right:** the selected title's episodes, or its seasons and other folders (Extras, Next
  page, …). Select an episode to play it, or a folder to open it in place. A ".." row or **Back**
  goes up a level, and **left** always returns to the titles, keeping your place. A movie or
  single video shows as one row.
- **Bottom right:** artwork and description of whatever is focused. For a title, this pane also
  shows where it comes from. A title with no picture of its own shows an empty stage.

DVR recordings appear automatically, one row per recording title. Everything else you add with
**Add to Center Stage** in the context menu, which appears on library items, recordings, add-on listings,
Favourites and home-screen widgets. A season you add is named after its show (so it joins any
other title of that name, such as the show's DVR recordings). When an add-on doesn't provide the
show name, you're asked for it.

## Contents

- [Using it](#using-it)
- [Integrating a skin](#integrating-a-skin)
  - [Opening the window](#opening-the-window)
  - [A home menu entry with its Stages](#a-home-menu-entry-with-its-stages)
  - [Widgets](#widgets)
  - [The background picture](#the-background-picture)
  - [A layout of your own](#a-layout-of-your-own)
- [Limits](#limits)
- [Development](#development)

## Using it

- Open it from **Programs** or **Video add-ons**.
- **Stages:** if your DVR files recordings in groups (MythTV recording groups), each group is a
  Stage. You're first asked which Stage to show, or "All Stages". When you add something with the
  context menu, you pick the Stage it belongs to, or all of them. Recordings outside any group
  folder (MythTV's "Show default recording group as root") are in the "Default" Stage.
- **Newest:** the first title, "<Stage> - Newest" (e.g. "All Stages - Newest"), lists the 25
  newest DVR recordings you see in the window, newest first, each named with its series. It
  stays first whatever the sort order. It can be turned off in the settings.
- **Movies:** add library movies, or movies from other add-ons, with the context menu, and pick
  their Stage like anything else. They're gathered under one "Movies" title (renamable); its
  context menu on each movie has "Stage…" and "Remove". Turn off "Group movies under
  one "Movies" title" in the settings to show each movie as its own title instead.
- In the window:
  - **Left/right** moves between titles and episodes.
  - **Back** returns to the titles, then to the Stage question (or closes the window).
  - **Context menu** on a title: Rename, Refresh, Remove (or Hide, for a DVR series), "Stage…"
    for titles you added, "Show hidden DVR series…", "Switch Stage…", "Settings…" and "Check
    for updates" (Kodi checks its add-on repositories, then installs or announces updates as
    its own update setting says).
  - A DVR series' episodes are Kodi's own recordings list, so the **context menu** on one is
    Kodi's (Delete, Edit, Information…), and **Clear** opens it too. Selecting one plays,
    resumes or shows information as Kodi's own "select action" setting says.
- **Widget:** point a skin widget at `plugin://script.centerstage/?action=list`, or
  `?action=list&group=Emily` for one Stage. Clicking a title opens the window on it.
- **Settings:** title sort order (A-Z or recently added), episode order, hide watched episodes
  (not in DVR series, whose lists always show every recording),
  group movies under "Movies", include DVR recordings, ask for a Stage when opening,
  show the "Newest" title, how see-through the panels are, and how long add-on listings are
  cached.

## Integrating a skin

Center Stage works with any skin as it is. A skin can go further with the hooks below, all
optional.

### Opening the window

```
RunScript(script.centerstage)                      the window; asks for a Stage first
RunScript(script.centerstage,group=Default)        straight into one Stage (a recording group)
RunScript(script.centerstage,ask=0)                All Stages, without asking
RunScript(script.centerstage,id=<entry id>)        on one title
```

Arguments are URL-encoded and joined with `&`, e.g. `group=Saved+for+Later&ask=0`. Recordings
outside any group folder are in the Stage `Default`, so `group=Default` works on every MythTV
setup. Opening on a Stage or a title skips the question, and Back on the titles closes the
window.

### A home menu entry with its Stages

`plugin://script.centerstage/?action=stages` lists the Stages: "All Stages", then each recording
group, Default first. Each item's `stage` property holds the `RunScript` arguments that open it,
so a list of them needs only one `onclick`:

```xml
<control type="list" id="24100">
	<content>plugin://script.centerstage/?action=stages</content>
	<onclick>RunScript(script.centerstage,$INFO[ListItem.Property(stage)])</onclick>
	<!-- item layouts with $INFO[ListItem.Label] -->
</control>
```

Pair it with a main-menu item that runs `RunScript(script.centerstage,group=Default)`, shown
with `<visible>System.HasAddon(script.centerstage)</visible>`. A white menu icon in Estuary's style is
in `resources/sidemenu.png` (`tools/art.py` draws it).

### Widgets

`plugin://script.centerstage/?action=list` lists the titles, and `&group=<name>` limits them to
one Stage. Clicking one opens the window on it. The items have art but no video info tag, so a
click opens the window instead of going through the user's "select action".

### The background picture

If the skin lets the user pick a background picture, it can share it with Center Stage through the
skin string **`centerstage.background`**: the picture's path while it's in use, empty when it's
not. Center Stage reads `Skin.String(centerstage.background)` from whatever skin is running. The
window draws the picture full-screen at 75% brightness over black, under its panels and the
focused title's fanart. When the string is empty, it uses its normal background. This works in
every layout, including the one for skins without their own.

Skin strings are saved with the skin's settings, so nothing has to run at start-up. The skin only
has to set the string when the user changes its background setting. If the skin has no such
setting yet, the simplest way is to store the picture there directly:

```xml
<control type="button">
	<label>Background picture</label>
	<label2>$INFO[Skin.String(centerstage.background)]</label2>
	<onclick>Skin.SetImage(centerstage.background)</onclick>
</control>
<control type="button">
	<label>No background picture</label>
	<onclick>Skin.Reset(centerstage.background)</onclick>
</control>
```

and draw it in the skin's own background with `$INFO[Skin.String(centerstage.background)]`,
visible when `!String.IsEmpty(Skin.String(centerstage.background))`.

A skin that already has its own setting keeps it, and sets `centerstage.background` alongside it
from the same buttons.  For example:

```xml
<control type="radiobutton">
	<label>Use custom background</label>
	<selected>Skin.HasSetting(use_custom_bg)</selected>
	<onclick condition="Skin.HasSetting(use_custom_bg)">Skin.Reset(centerstage.background)</onclick>
	<onclick condition="!Skin.HasSetting(use_custom_bg)">Skin.SetString(centerstage.background,"$INFO[Skin.String(custom_background)]")</onclick>
	<onclick>Skin.ToggleSetting(use_custom_bg)</onclick>
</control>
<control type="button">
	<label>Choose image path</label>
	<onclick>Skin.SetImage(custom_background)</onclick>
	<onclick>Skin.SetString(centerstage.background,"$INFO[Skin.String(custom_background)]")</onclick>
	<enable>Skin.HasSetting(use_custom_bg)</enable>
</control>
```

The quotes keep a path with commas in one piece.


Or leave the string empty and draw the background in a layout of your own (below).

### A layout of your own

Kodi looks for the window in `resources/skins/<skin id>/<folder>/script-centerstage-main.xml`
before falling back to `resources/skins/Default/1080i/`. `<folder>` must be the skin's own
resolution folder name (`<res folder=...>` in its `addon.xml`, e.g. `xml` for Estuary). The
Estuary layout is the one to start from. It shows the control ids (100 titles, 101 their
scrollbar, 200 episodes, 201 its scrollbar) and the window and list item properties the add-on
fills in. `tests/test_skins.py` checks that every layout has them.

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

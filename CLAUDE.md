# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`script.centerstage` is a Kodi 21/22 add-on. It shows a three-pane window: all titles on the
left, the selected title's episodes top right, and details bottom right. Titles come from:
- DVR recordings: automatic, one row per recording title
- the video library: added by the user
- other add-ons' folders and items: added by the user

Users add titles with the "Center Stage…" context menu entry. The same list is also exposed as a
plugin folder, for widgets.

The design constraints (no Kodi core changes allowed) and the feasibility analysis are in the
approved plan: `~/.claude/plans/we-want-to-make-linear-magpie.md`. `../xbmc` is a Kodi master
(22) checkout for checking claims against source. It is the user's fork and not part of this
project: its `addons/skin.estuary` carries their own skin changes, and it may move. Check stock
Estuary against the Flatpak 21.3 copy
(`/var/lib/flatpak/app/tv.kodi.Kodi/x86_64/stable/active/files/share/kodi/addons/skin.estuary`),
and ask the user if you need a particular version checked out.

## Commands

- Tests: `python3 -m unittest discover tests`
- One test: `python3 -m unittest tests.test_classify -k season`
- Syntax: `python3 -m py_compile default.py plugin.py context.py resources/lib/*.py resources/lib/sources/*.py`
- Install into the Flatpak Kodi (21.3): `tools/install.sh`. The log is at
  `~/.var/app/tv.kodi.Kodi/data/temp/kodi.log`, and our lines start with `script.centerstage: `.

## Layout

The add-on has three entry points, all declared in `addon.xml`. Each one puts `resources/lib` on
`sys.path`.
- `default.py`: the `xbmc.python.script` extension (listed under Programs). It opens the window.
  `RunScript(script.centerstage,id=<urlencoded entry id>)` preselects a title, and `&group=`
  picks a recording group. `ask=0` opens all groups without asking. A Home window property stops a second copy from opening.
- `plugin.py`: the `xbmc.python.pluginsource` extension (listed under Video add-ons).
  - Root: opens the window, with no listing in between. Only when Home is the active window
    (a widget pointed at the root) does it list the titles instead. Opening the plugin from
    anywhere else activates the Videos window before the plugin runs.
  - `?action=list`: widget listing. `&group=` limits it to one recording group.
  - `?action=open&id=`: opens the window on a title (`&group=` and `&ask=0` too).
  - `?action=stages`: the recording groups ("Stages" in the skin), "All groups" first, for Myth
    Estuary's "Center Stage" home menu entry. Each item's `stage` property is the urlencoded
    `RunScript` arguments that open it without asking; the skin's `<onclick>` uses that rather
    than the item's path, so the click doesn't go through `PlayMedia`.

  Widget items deliberately have **no video info tag**. With one, a click would go through the
  user's video "select action" (e.g. show information) instead of `PlayMedia`, and our plugin
  answers `PlayMedia` with `setResolvedUrl(False)`.
- `context.py`: the `kodi.context.item` extension. It copies `sys.listitem`, plus
  `Container.PluginCategory` and the `ParentPath` property, into a `classify.Snapshot`, and builds
  a menu from `classify.candidates()`. After naming, it asks which recording group the entry is
  for (see Recording groups below).

Modules in `resources/lib/` are Kodi-free (unit-tested) except `kodiutil.py` and `window.py`:
- `model.py`: `Entry` (a left row) and `Episode` (a right row), plus `entry_id()`. Ids are
  deterministic, e.g. `library:season:4:2`, `pvr:<casefolded title>`, `addon:<kind>:<url>`, so
  adding the same thing twice is detected. An `Episode` with no name of its own (none, blank or
  "Untitled", `model.is_untitled()`) is flagged `untitled`. `kodiutil.episode_label()` then shows
  it as "Season X, Episode Y" in every layout, when the numbers are known. Rows show a named
  episode's name only. The details pane's `name` property (`kodiutil.details_name()`) adds
  "S01E02 · ".
- `store.py`: `entries.json` in the add-on profile. It holds the entries, hidden DVR series
  (`{key: title}`), renames of computed entries and `last_group` (the group last picked). Every write re-reads the file first, because
  the context script and the window are separate interpreters.
- `classify.py`: what can be added from an item, and the show-name chain for season folders.
- `sources/`: `library.py`, `pvr.py` and `addon.py`, one per source, each built on
  `jsonrpc.Rpc`. Each returns **one level** of rows: `Episode`s that are either playable (`play`)
  or folders (`is_folder`, plus a `browse` dict that is passed back to list them).
  - Library shows list their seasons (`VideoLibrary.GetSeasons`), or go straight to the episodes
    when there's only one season.
  - Add-on folders are listed exactly as the add-on returns them, except that an add-on's own
    "..", "Back" or ".. Back" folder (`addon.is_back()`) is dropped at the entry's top level,
    where the way back is the titles list. When a folder holds a single subfolder, it's opened
    automatically.
  - Nothing is flattened or guessed.

  `catalog.py` sorts and mixes the rows, dispatches `load_rows()`, and `arrange()`s a level.
  `arrange()` keeps folders in their places.
- `cache.py`: add-on levels on disk, keyed by `window.level_key(entry id, browse)`, with the TTL
  taken from the `cache_minutes` setting.
- `window.py`: the `WindowXML`. See the notes below.

The top-right list is a browser:
- Each title keeps a stack of opened folders in `window.stacks`, for this window session only.
- A `..` row (`model.parent_row()`, only below the top level) and the Back action
  (`ACTION_NAV_BACK`) go up a level. When there's no level left, Back moves focus to the titles. Esc (`ACTION_PREVIOUS_MENU`)
  closes the window.
- **Left arrow is handled by the skin's `<onleft>100</onleft>` and must never pop the stack.**
  Going right again returns to the same folder.

There are three layouts. `WindowXML` looks in `resources/skins/<current skin id>/` before
`Default/` (`WindowXML.cpp:107-139`). **In that per-skin folder, the subfolder must have the
skin's own resolution folder name** (`xml` for Estuary and Myth Estuary, from `<res folder=>` in
the skin's addon.xml). The branch that would scan it for `1080i` etc. is guarded by
`CFileUtils::Exists(basePath)`, which is always false for a directory (`CPosixFile::Exists`
rejects `S_ISDIR`). A `1080i` folder there was silently skipped, and the Default layout was used
instead. `Default/` itself does use `1080i`: that last fallback scans the folder.
- `resources/skins/skin.estuary/xml/`: uses Estuary's includes (`ColoredBackgroundImages`,
  `TopBar`, `ContentPanel`, `OpenClose_*`), `$VAR[ListWatchedIconVar]`, its fonts and its colours
  (`button_focus`, `grey`, `text_shadow`), and its scrollbar and progress defaults. All of these
  exist in stock Estuary 21.3 and 22.
  **Don't reference a colour name the skin lacks: it becomes fully transparent.**
  **Don't assume a 1920-wide screen.** A per-skin layout uses that skin's coordinate space, and
  Estuary declares several (1920, 2040, 2160, 2338 or 2560 wide, all 1080 tall). Kodi picks the
  one closest to the window's aspect ratio (`CSkinInfo::GetSkinPath`, `closestRes`). The user's
  windowed Kodi is about 1.91:1, so it gets 2040. Anchor the right-hand side with `<right>`, and
  centre things with `<centerleft>50%</centerleft>`. The Default layout has only `1080i`, so it is
  always 1920x1080.
- `resources/skins/skin.myth-estuary/xml/`: for Myth Estuary, the user's Estuary fork (the skin
  in `../xbmc/addons/skin.estuary`, with id `skin.myth-estuary`). From `<window>` down it is a
  byte-for-byte copy of the Estuary layout; `tests/test_skins.py` enforces this. Edit the Estuary
  file, then copy it over.
- `resources/skins/Default/1080i/`: for every other skin. It reproduces the Estuary layout with
  nothing from the skin. It uses the same positions (fixed 1920x1080, which matches Estuary's
  16:9 space), Estuary's default blue `FF12A0C7` and grey `FFA0A0A0`, and `[B]` where Estuary
  uses its bold `*_title` fonts.
- **The user wants all three layouts to look very close: the same positions, similar font sizes,
  the same emphasis.** Change the Estuary layout first, then carry the change to Default and copy
  it to Myth Estuary. If you move something in one layout, move it in the others too.
- The layout was modelled on a three-pane Estuary recordings view (the user's `MyPVRRecordings.xml`):
  - a 550px titles column
  - an episode list with the date on the right (`Label2`, plus the time for recordings)
  - details with the title's name, the episode's name, and a grey block of channel, date and
    length (the `details` property from `kodiutil.episode_details()`), plus the thumbnail and plot.
    In the Estuary layout, which was reworked at the user's request, the details pane follows
    `../xbmc/addons/skin.estuary/xml/MyPVRRecordings.xml`:
    - the title's name, with the episode's name (with S01E02) under it
    - opposite them, right-aligned in grey: the episode's `details`, or the title's `origin`
    - **below** those, the picture on the left in a 480x270 box (16:9 fills it, 4:3 fills its
      height), with the plot beside it in `font12`, smaller than the lists' `font27`. The picture
      is the title's `thumb` (a landscape image when there is one; see
      `kodiutil.listitem_art()`) or the episode's.
    - every control is in the same place whichever list has focus, so nothing jumps while
      navigating; only the contents swap (`Control.HasFocus(200)`)
    - the panes are 30px apart, and the right-hand panels run off the right edge of the screen.
      Scrollbars sit flush with their panel's visible edge, and the episodes' one is at the
      screen edge.
- Control 100 is the titles list. It is a plain `list`, so the first title is at the top. The user
  rejected a `fixedlist` (the recordings window's choice), because it leaves empty space above
  the first title. Its selected row keeps a dimmed highlight while the episodes have
  focus. Control 200 is the episodes list. 101 and 201 are their scrollbars, which are for mouse and
  touch only: no list navigates onto them.
- The details pane is pure XML (`Container(100|200).ListItem.*` switched on `Control.HasFocus(200)`).
- Window properties used:
  - `loading`, `message`, `empty`
  - `group`: the recording group shown, empty for all of them (in the breadcrumbs)
  - `level`: the path of the open folder, e.g. "Season 2 / Extras"
  - `dvr`: PVR answered, which gates the backend disk-space bar
- The skin-facing hooks (RunScript arguments, `?action=stages`, widgets, the background
  string, per-skin layouts) are documented for skin authors in README "Integrating a skin";
  keep it in step. The background is `Skin.String(centerstage.background)` of the running skin:
  a path while in use, empty otherwise. It's persistent, so it works without anything running at
  start-up (the user rejected a Home window property for that reason). Myth Estuary sets it
  alongside its own `use_custom_bg`/`custom_background` from the same skin-settings buttons, and
  keeps drawing its own background from those (the user didn't want the skin reading our string). Every layout draws it at 75% over black when set, below the fanart;
  in the Estuary/Myth layout that covers `ColoredBackgroundImages`, so Myth Estuary's own copy of
  the picture isn't drawn twice over itself.
- The disk-space bar reads `PVR.BackendDiskSpaceProgr` (255 when not reported). Only reading the
  `PVR.BackendDiskSpace` label makes Kodi refresh those numbers, so `_refresh` reads it.
- The Default layout uses only fonts that every skin has (`font12`/`font13`; Kodi falls back to
  `font13`), plus `uv-white.png`. Its panels, focus bars, scrollbars and progress bar set every
  texture, so the current skin's defaults don't leak in. Where Estuary shows a watched icon, it
  shows a dot for unwatched items, at half brightness when partly watched.

## Recording groups

- A recording's group is its JSON-RPC `directory` minus the trailing title folder
  (`pvr.group_of()`). pvr.mythtv files recordings as `<recording group>/<title>`, or just
  `<title>` for Default when its "Show default recording group as root" setting is on (its
  default; the user has it off). Anything left with no group folder is put in `pvr.DEFAULT_GROUP`
  ("Default"), so the Default group, and the skin's `group=Default`, work with the setting either
  way; backends without groups put every recording in Default. `pvr.groups()` lists Default
  first. pvr.mythtv also wraps damaged recordings' titles in `[COLOR yellow]`, which
  `pvr._title()` strips so they join their series. Only the episode row keeps the colour:
  titles go through `model.plain()`, and the details pane shows the episode's `name` property
  (its label without tags) instead of `ListItem.Label`.
- `window.show()` asks for a group (`Dialog.select`: "All groups" plus each group, preselecting
  `last_group`) when there are two or more groups, the `ask_group` setting is on, and nothing was
  preselected. Back on the titles (or "Switch recording group…") closes the window and asks
  again. Cancelling the question closes everything.
- In a group, the window shows only that group's recordings, so a DVR title's episodes are that
  group's only. Stored entries have `Entry.group`: `""` means all groups, otherwise one group
  name (`catalog.rows(..., group)` filters). "Recording group…" in the title menu changes it.

## Movies

- Movies are stored entries of kind `MOVIE` (library movies, and add-on items whose media type is
  movie), added and given a group like anything else.
- With the `group_movies` setting on (the default), `catalog.rows(..., movies_title)` gathers the
  movies shown in that group into one computed `Entry` (`source=MOVIES`, id `movies`, the movies
  in `Entry.members`). `catalog.movie_rows()` gives one row per movie, by its Center Stage name
  and sorted by it, with `Episode.entry_id` set to the movie's entry. The episode order and
  "hide watched" settings don't apply to it.
- The "Movies" title can be renamed (stored in `renames` under `movies`, read by
  `kodiutil.movies_title()`), but not removed or given a group. Each movie's own context menu in
  the episode list has "Recording group…" and "Remove" instead.
- With the setting off, every movie is its own title, as before.
- DVR recordings of movies aren't detected; they're titles like any other recording.

## Kodi facts this code relies on (checked in ../xbmc)

- **Module globals don't survive between invocations.** Every run of an entry point (a
  `RunScript`, each plugin URL Kodi lists or resolves, each context-menu click) starts a fresh
  interpreter. Only callbacks inside one run (e.g. `onAction` while `doModal` is up) share state.
  Anything that has to outlive a run goes in the profile (`store.py`, `cache.py`), the add-on
  settings, or a window property (e.g. Home's `script.centerstage.open` in `default.py`). Never
  cache in a global and expect the next widget refresh or menu click to see it.
- **PVR recordings:** JSON-RPC `title` is the show name and `showtitle` is the **episode name**
  (`CPVRRecording`: `strEpisodeName` → `m_strShowTitle`). Season and episode are -1 when the
  backend doesn't know them. `starttime` is **UTC**, so `pvr._local()` converts it before it's
  shown.
- **`Files.GetDirectory` with `media:"files"`** and non-basic properties loads play counts and
  resume points from the video DB on **22+ only** (`FileOperations.cpp` `NeedsLibraryLookup`).
  `sources/addon.py` switches on the major version. Plugin directories ignore the extension mask
  (`AllowAll`).
- **`Container.FolderName`** in a plugin listing is the add-on's name, not the folder's name. That
  is why season naming uses the item's `TVShowTitle`, then `Container.PluginCategory`, then an
  episode's `showtitle`, and finally asks the user.
- **WindowXML** has no selection-changed callback, so `window._watch` polls the left list every
  50 ms and loads after it has been still for 100 ms. Loads run in threads, and a generation counter
  drops stale results. Controls are updated only while holding `self.lock`.
- **The window must be a `WindowXML`, not a dialog,** so fullscreen video covers it. `onInit`
  runs again when playback stops, and `window.py` treats that as a refresh.
- **Kodi's resume prompt** isn't shown for `Player.Open`, so `_play` asks the user and passes
  `options.resume`.

## Not verified in a running Kodi yet

Only the unit tests and a stub-based smoke run have been done. Things to check in a real Kodi:
- where the add-on shows up (Programs, Video add-ons) and that both launch the window
- the context entry in plugin listings, the PVR recordings window, Favourites and widgets
- `Files.GetDirectory` against real add-ons (`../plugin.video.hoopla`, `../plugin.video.the-chosen`)
- playback from the window, and the window coming back afterwards
- resume points for add-on items
- what hoopla and the-chosen report for `TVShowTitle` and `PluginCategory` on season folders
- all three layouts (only checked as XML; Myth Estuary isn't installed in the Flatpak Kodi), and the
  disk-space bar
- folder browsing in real add-ons
- the widget click path (`PlayMedia` → `RunScript`) and whether it shows an error
- Myth Estuary's "Center Stage" home entry (in that skin's `Home.xml`: the first menu item,
  and the Stages panel, group 24000 with list 24100, modelled on Recordings' 22000/22100;
  icon `media/icons/sidemenu/centerstage.png`, copied from `resources/sidemenu.png`; hidden by
  the `HomeMenuNoCenterStageButton` toggle in Skin settings → Main menu items)
- the "Movies" title, and the Default group with pvr.mythtv's "Show default recording group as
  root" on
- Kodi 22

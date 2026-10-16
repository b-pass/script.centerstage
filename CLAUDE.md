# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`script.centerstage` is a Kodi 21/22 add-on. It shows a three-pane window: all titles on the
left, the selected title's episodes top right, and details bottom right. Titles come from PVR
recordings (automatic, one row per recording title), the video library and other add-ons'
folders and items (both added with the "Add to Center Stage" context menu entry). The list is
also a plugin folder, for widgets.

The design constraints (no Kodi core changes allowed) are in the approved plan:
`~/.claude/plans/we-want-to-make-linear-magpie.md`. `../xbmc` is a Kodi master (22) checkout for
checking claims against source. It's the user's fork, not part of this project, and may move; its
`addons/skin.estuary` carries their own skin changes. Check stock Estuary against the Flatpak 21.3
copy (`/var/lib/flatpak/app/tv.kodi.Kodi/x86_64/stable/active/files/share/kodi/addons/skin.estuary`),
and ask the user if you need a particular version checked out.

## Working with the user

- **Ask before building something exceptionally cumbersome.** That means a lot of code, or a
  fight with Kodi: an info label with no text form, a missing callback, something only a core
  change could do cleanly. Workarounds count, even short ones: scraping numbers out of display
  strings, polling for something Kodi doesn't report, duplicating a skin include. (A "89.1%" disk
  space built by parsing the localised `PVR.BackendDiskSpace` text was refused after the fact.)
  Say briefly what makes it costly and offer options, including a simpler version or dropping it.
  The user often can't tell how much work a request is. Ordinary features: just build them.
- **Keep this file to rules, pitfalls, decisions and pointers.** No change history ("was X, the
  user asked for Y", "once broke because…"), no restating what the code plainly does, no pixel
  values or font names that live in the layout XML. Record a user decision as one line of what
  holds now, and only when it stops something being redone or undone.

## Commands

- Tests: `python3 -m unittest discover tests`
- One test: `python3 -m unittest tests.test_classify -k season`
- Syntax: `python3 -m py_compile default.py plugin.py context.py resources/lib/*.py resources/lib/sources/*.py`
- Install into the Flatpak Kodi (21.3): `tools/install.sh`. The log is at
  `~/.var/app/tv.kodi.Kodi/data/temp/kodi.log`; our lines start with `script.centerstage: `.
- Art (icon, fanart, `stage.jpg`, `sidemenu.png`): `python3 tools/art.py` (needs Pillow).

## Code layout

Three entry points, all in `addon.xml`; each puts `resources/lib` on `sys.path`.
- `default.py` (`xbmc.python.script`, under Programs) opens the window. `RunScript` arguments:
  `id=<urlencoded entry id>`, `group=`, `ask=0`. A Home window property stops a second copy.
- `plugin.py` (`xbmc.python.pluginsource`, under Video add-ons). The root opens the window, except
  when Home is active (a widget pointed at the root), where it lists titles. `?action=list`
  (`&group=`) is the widget listing, `?action=open&id=` opens a title, `?action=stages` lists the
  Stages with each item's `stage` property holding the `RunScript` arguments (the skin's
  `<onclick>` uses that, so the click doesn't go through `PlayMedia`). Widget items deliberately
  have **no video info tag**: with one, a click goes through the user's "select action" instead of
  `PlayMedia`, which we answer with `setResolvedUrl(False)`.
- `context.py` (`kodi.context.item`) snapshots `sys.listitem`, `Container.PluginCategory` and
  `ParentPath` into a `classify.Snapshot` and builds the menu from `classify.candidates()`.

`resources/lib/` is Kodi-free and unit-tested, except `kodiutil.py` and `window.py`:
- `model.py`: `Entry` (left row), `Episode` (right row), deterministic `entry_id()`s so adding
  something twice is detected.
- `store.py`: `entries.json` in the profile. Every write re-reads the file first: the context
  script and the window are separate interpreters.
- `classify.py`: what can be added from an item, and the show-name chain for seasons.
- `sources/` (`library`, `pvr`, `addon`): each returns **one level** of rows, playable or folders
  with a `browse` dict passed back to open them. Nothing is flattened or guessed; an add-on's own
  "..", "Back" folder is dropped at an entry's top level.
- `catalog.py` mixes and sorts titles and dispatches `load_rows()`; `arrange()` keeps folders in
  place. `cache.py` keeps add-on levels on disk (`cache_minutes`).

The top-right list is a browser: each title keeps a stack of opened folders (`window.stacks`);
the `..` row and Back go up, Back at the top moves to the titles, Esc closes.
**Left arrow is the skin's `<onleft>100</onleft>` and must never pop the stack.**

## Layouts

`WindowXML` looks in `resources/skins/<current skin id>/` before `Default/`. **In a per-skin
folder the subfolder must be the skin's own resolution folder name** (`xml` for Estuary and Myth
Estuary): a `1080i` folder there is silently skipped (`CFileUtils::Exists` is false for
directories). `Default/` itself uses `1080i`.
- `skin.estuary/xml/` uses Estuary's includes (`ColoredBackgroundImages`, `TopBar`,
  `OpenClose_*`), `$VAR[ListWatchedIconVar]`, its fonts and colours, all present in 21.3 and 22.
  **A colour name the skin lacks becomes fully transparent.** **Don't assume 1920 wide:** Estuary
  has several coordinate spaces (1920-2560 wide) and Kodi picks the closest aspect; the user's
  windowed Kodi gets 2040. Anchor the right side with `<right>`, centre with `<centerleft>50%`.
- `skin.myth-estuary/xml/` is for Myth Estuary, the user's Estuary fork (`../xbmc/addons/
  skin.estuary`). From `<window>` down it's a byte-for-byte copy of the Estuary layout
  (`tests/test_skins.py`): edit Estuary, then copy. Myth Estuary is unreleased: keep it out of
  the README; describe skin hooks generically there.
- `Default/1080i/` is for every other skin, a fixed 1920x1080 copy of the Estuary layout using
  only `uv-white.png`, its own colours and common fonts (`font12`-`font14`; Kodi falls back to
  `font13`). It sets every texture so the skin's defaults don't leak in.
- **All three layouts must look alike: same positions, similar font sizes, same emphasis.**
  Change Estuary first, carry it to Default, copy to Myth.

Layout rules (the numbers are in the XML):
- Modelled on Myth Estuary's recordings window (`../xbmc/addons/skin.estuary/xml/
  MyPVRRecordings.xml`), including its font sizes; users compare the two.
- Every control stays put whichever list has focus; only contents swap (`Control.HasFocus(200)`
  and `(210)`).
  The details pane is pure XML.
- Panels are 30px apart and 30px from the screen edges, all ending on the same line; lists are a
  whole number of rows; lists run up to their scrollbars; the details panel has equal inner
  margins. **A panel image's 20px border is shadow**: the image is 40px bigger than what shows.
- Top bar: "Center Stage" over the Stage (`group` property), as `TopBar`'s breadcrumbs and
  sublabel. Its clock ends where the right panels do (`TopBar` sits in a group 10px narrower).
- Panel opacity is the `panel_opacity` setting. The colours are Home properties
  (`kodiutil.set_home_properties()`, with the recordings sort order) because a texture's
  `colordiffuse` is evaluated with no window context, so our own window's property isn't
  reliably found.
- Control 100 (titles) is a plain `list`, not a `fixedlist` (the user rejected the gap above the
  first title); its selected row stays dimly highlighted while 200 or 210 (episodes) has focus.
  101, 201 and 211 are mouse/touch-only scrollbars.
- **A PVR series' episodes are Kodi's own list (control 210, `<content>` of the series'
  `pvr://` folder, `pvr.folder_of()`), not Python rows.** Kodi's recording menu (Delete, Edit,
  …) only exists for items Kodi lists, and add-ons can't delete recordings any other way. Don't
  replace it with Python rows, and don't fake the menu (an invisible dialog doing that was built
  and removed). The user accepted the costs: "hide watched" doesn't apply there, a click follows
  Kodi's video select action, in All Stages a series shows only the Stage of its newest
  recording, and rows/details are built in XML from Kodi's fields (`EpisodeName`, `Season`,
  `Episode`, `Date`, …), since Kodi labels a recording with the show's title. Every layout has
  both lists; Newest, Movies, library and add-on titles use 200.
- **Switching must be as quick as Myth Estuary's** (whose title rows `Container.Update` the
  episodes `onfocus`). So 210's `<content>` and the 200/210 switch read the selected title's
  `folder` property (`Container(100).ListItem.Property(folder)`, set in `entry_listitem`) and
  change the moment the selection moves, with no Python in between. `_watch` also switches at
  once to rows it already has (`_at_hand`); only rows that need loading wait for `SETTLE`.
- No flicker while moving through titles: "Loading…" appears only after 250 ms, and 210 is
  hidden while Kodi fetches (it would show the previous series' rows) unless it has focus
  (`allowhiddenfocus`, so focus can still move there). No fade-ins: they make switching feel
  slow.
- Kodi tells add-ons nothing when recordings change (no PVR announcement), so `_watch` also
  reads Kodi's list (`_recordings_shown`: the selected series' folder and 210's count, once it's
  done filling and two reads agree) and refreshes the titles when the count changes for the same
  series: a delete from Kodi's menu, or a recording finishing. The user chose this over
  refreshing after the menu closes.
- Newest stays our own Python rows (they skip hidden series) with our own small menu.
- The titles list shows no watched status; the user doesn't want icons there.
- A title's picture is its `thumb`; for PVR series that's the series fanart, not pvr.mythtv's
  preview image, which is for episodes (as in the recordings window). No picture: `stage.jpg`.
- The background is `Skin.String(centerstage.background)` of the running skin, a persistent
  string so nothing has to run at start-up (the user rejected a Home property). Myth Estuary sets
  it alongside its own background settings; its "Monthly background" clears it and reaches us
  only through `ColoredBackgroundImages`.
- The disk-space text: `PVR.BackendDiskSpaceProgr` has no label form, so `_watch` bisects it with
  `Integer.IsGreater`. Only reading the `PVR.BackendDiskSpace` label makes Kodi refresh the
  numbers; that's done on open and every 15 minutes.
- The skin-facing hooks (`RunScript` arguments, `?action=stages`, widgets, the background
  string, per-skin layouts) are documented in README "Integrating a skin"; keep it in step.

## Recording groups ("Stages")

- Users only ever see "Stage"; code, `group=` arguments and the `group` property say group.
- Say "PVR", as Kodi does, never "DVR": in what users see and in the code.
- A recording's group is its JSON-RPC `directory` minus the title folder (`pvr.group_of()`).
  Recordings with no group folder (pvr.mythtv's "Show default recording group as root") are in
  `pvr.DEFAULT_GROUP`, so `group=Default` works either way. The user keeps the name "Default".
- pvr.mythtv wraps damaged recordings' titles in `[COLOR yellow]`; titles are stripped
  (`model.plain()`) so they join their series, and only the episode row keeps the colour.
- Stored entries have `Entry.group` (`""` = all Stages). In a Stage, PVR titles show only that
  Stage's recordings.
- `window.show()` asks which Stage (preselecting `last_group`) when there are two or more, the
  `ask_group` setting is on and nothing was preselected. Back on the titles, or "Switch Stage…",
  asks again; cancelling closes everything.

## Computed titles

- **Movies** (`group_movies`): stored movies gathered into one renamable title (`Entry.members`);
  each movie's row menu has "Stage…" and Remove. Episode order and hide-watched don't apply.
- **Newest** (`show_newest`): "<Stage> - Newest", always first, the 25 newest shown recordings
  (`pvr.NEWEST_LIMIT`, counted after hiding watched ones), each prefixed with its series.
  `ref['titles']` holds the shown series, so hidden ones stay out and renames show.
- **Same-named titles are deliberately not merged**: each title's rows come from one place and
  its menu acts on one thing. Merging was built and removed as too complex for what it gave.
- Added seasons are named after the show; menus still say "Show - Season N" via
  `classify.season_description()`.

## Kodi facts this code relies on (checked in ../xbmc)

- **Module globals don't survive between invocations.** Every `RunScript`, plugin URL and
  context-menu click is a fresh interpreter; only callbacks inside one run share state. Persist in
  the profile, the settings, or a window property.
- **PVR recordings:** JSON-RPC `title` is the show and `showtitle` is the **episode name**.
  Season/episode are -1 when unknown. `starttime` is **UTC** (`pvr._local()`).
- **`Files.GetDirectory`** loads play counts and resume points for add-on items on **22+ only**
  (`NeedsLibraryLookup`); `sources/addon.py` switches on the version.
- **`Container.FolderName`** in a plugin listing is the add-on's name, so season naming uses
  `TVShowTitle`, then `Container.PluginCategory`, then an episode's `showtitle`, then asks.
- **WindowXML** has no selection-changed callback: `_watch` polls the left list. Loads run in
  threads; a generation counter drops stale results; controls change only under `self.lock`.
- **The window must be a `WindowXML`, not a dialog,** so fullscreen video covers it. `onInit`
  runs again after playback; that's treated as a refresh.
- **`Player.Open` shows no resume prompt**, so `_play` asks and passes `options.resume`.
- **`Addon.openSettings()`** edits the calling `Addon` object's own settings, so `K.ADDON` is
  current afterwards.
- **`UpdateAddonRepos`** checks every repository; Kodi can't check one add-on.
- **Add-ons can't delete recordings** (no JSON-RPC method, builtin or `pvr://` file support), and
  Kodi's item context menu (`CONTEXTMENU::ShowFor`) only opens for items Kodi listed itself. But a
  list filled from `<content>` in any window gets it (`CDirectoryProvider::OnContextMenu`), and
  `CGUIWindow::OnAction` gives the focused control the key before Python's `onAction`. Don't
  fake it with an invisible dialog that lists the folder and sends the menu key: that was built
  and removed.
- **`Container(id)` from Python, with no window context, resolves to the topmost dialog**, then
  the active window (`GUIInfoHelper::GetWindowWithCondition`).

## Not verified in a running Kodi yet

Only unit tests and stub-based smoke runs so far. To check in a real Kodi:
- where the add-on shows up, the context entry (plugin listings, recordings, Favourites, widgets)
- `Files.GetDirectory`, `TVShowTitle`/`PluginCategory` and folder browsing in real add-ons
  (`../plugin.video.hoopla`, `../plugin.video.the-chosen`)
- playback, resume points, and the window coming back afterwards
- all three layouts and the disk-space text (Myth Estuary isn't installed in the Flatpak Kodi)
- the widget click path (`PlayMedia` → `RunScript`)
- Myth Estuary's "Center Stage" home entry and Stages panel (its `Home.xml`, group 24000/list
  24100; icon copied from `resources/sidemenu.png`; hidden by `HomeMenuNoCenterStageButton`)
- Kodi's recordings list (210): that the folder lists the series, its context menu (Delete)
  and refresh after a delete, Clear reaching the window, the sort order, the XML-built rows and
  details, focus moving between the lists
- the Movies and Newest titles; the Default group with "Show default recording group as
  root" on; panel opacity; "Check for updates"; Kodi 22

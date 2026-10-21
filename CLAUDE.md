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
  strings, polling for something Kodi doesn't report, duplicating a skin include. Say briefly
  what makes it costly and offer options, including a simpler version or dropping it. The user
  often can't tell how much work a request is. Ordinary features: just build them.

## Keeping this file useful

This file is read at the start of every session; each line costs attention. Before adding to
it, ask whether a future session would do the wrong thing without that line, and whether the
code and its comments would already stop it.
- **Only rules, pitfalls, decisions and pointers.** How something works belongs in a comment
  next to the code; here, at most a pointer (`window.RecordingMenu`). No pixel values, fonts,
  timings or constants that live in the code or the XML.
- **No history.** Not what was tried, removed, refused or changed, nor who asked when. If a
  removed approach must not come back, one line: "Don't X: <the reason, in a clause>". A user
  decision is one line of what holds now.
- **Edit, don't append.** When a change touches something covered here, rewrite that line, and
  delete lines that no longer hold. Merge into an existing bullet before starting a new one.
- **Length is fine; noise isn't.** A long file of live rules is better than a short one missing
  them, but stale or obvious lines bury the ones that matter. Past about 350 lines, look for
  lines to cut or merge before adding.

## Commands

- Tests: `python3 -m unittest discover tests`
- One test: `python3 -m unittest tests.test_classify -k season`
- Syntax: `python3 -m py_compile default.py plugin.py context.py resources/lib/*.py resources/lib/sources/*.py`
- Install into the Flatpak Kodi (21.3): `tools/install.sh`. The log is at
  `~/.var/app/tv.kodi.Kodi/data/temp/kodi.log`; our lines start with `script.centerstage: `.
- Art (icon, fanart, `stage.jpg`, `sidemenu.png`, `spinner.png`): `python3 tools/art.py` (needs Pillow).

## Code layout

Three entry points, all in `addon.xml`; each puts `resources/lib` on `sys.path`.
- `default.py` (`xbmc.python.script`, under Programs) opens the window. `RunScript` arguments:
  `id=<urlencoded entry id>`, `group=`, `ask=0`.
- `plugin.py` (`xbmc.python.pluginsource`) **provides `executable`, and must provide
  something**: the content type decides where Kodi lists the add-on (the user wants Programs),
  and with none, `RunAddon` (every launch from Kodi's own menus, Favourites, JSON-RPC) falls
  back to `RunPlugin(<id>)`, which does nothing. `RunAddon` opens the Programs window on the
  plugin root, which opens ours, so Back lands in Programs (accepted).
- **The plugin extension must come first in `addon.xml`**: Kodi's add-on widgets
  (`CAddonsDirectory::GetScriptsAndPlugins`) list a `plugin://` path as a folder only for a
  main-type plugin. `RunScript` still runs `default.py`.
- Don't close Kodi's window from the script: it can close the wrong one.
- Plugin URLs: the root (handle ≥ 0) lists titles when Home is active (a widget), otherwise
  opens the window; `?action=list&group=` is the widget listing; `?action=open&id=` opens a
  title; `?action=stages` lists the Stages, each with a `stage` property of `RunScript`
  arguments for the skin's `<onclick>`. Widget items have **no video info tag**: with one, a
  click follows the user's "select action" instead of `PlayMedia`.
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
Estuary): a `1080i` folder there is silently skipped. `Default/` itself uses `1080i`.
- `skin.estuary/xml/` uses Estuary's includes (`ColoredBackgroundImages`, `TopBar`,
  `OpenClose_*`), `$VAR[ListWatchedIconVar]`, its fonts and colours, all present in 21.3 and 22.
  **A colour name the skin lacks becomes fully transparent.** **Don't assume 1920 wide:** Estuary
  has several coordinate spaces (1920-2560 wide); the user's windowed Kodi gets 2040. Anchor the
  right side with `<right>`, centre with `<centerleft>50%`.
- `skin.myth-estuary/xml/` is for Myth Estuary, the user's Estuary fork (`../xbmc/addons/
  skin.estuary`). From `<window>` down it's a byte-for-byte copy of the Estuary layout
  (`tests/test_skins.py`): edit Estuary, then copy. Myth Estuary is unreleased: keep it out of
  the README; describe skin hooks generically there.
- `Default/1080i/` is for every other skin, a fixed 1920x1080 copy of the Estuary layout using
  only `uv-white.png`, its own colours and common fonts. It sets every texture so the skin's
  defaults don't leak in.
- **All three layouts must look alike: same positions, similar font sizes, same emphasis.**
  Change Estuary first, carry it to Default, copy to Myth.

Layout rules:
- Modelled on Myth Estuary's recordings window (`../xbmc/addons/skin.estuary/xml/
  MyPVRRecordings.xml`), including its font sizes; users compare the two.
- Every control stays put whichever list has focus; only contents swap (`Control.HasFocus(200)`).
  The details pane is pure XML.
- Panels are 30px apart and 30px from the screen edges, all ending on the same line; lists are a
  whole number of rows and run up to their scrollbars; the details panel has equal inner
  margins. **A panel image's 20px border is shadow**: the image is 40px bigger than what shows.
- Top bar: "Center Stage" over the Stage (`group` property), as `TopBar`'s breadcrumbs and
  sublabel; its clock ends where the right panels do.
- Panel opacity is the `panel_opacity` setting. Colours are Home properties
  (`kodiutil.set_home_properties()`): a texture's `colordiffuse` is evaluated with no window
  context, so our window's own property isn't reliably found.
- The titles (100) scroll with the focus in the middle, like Estuary's List view (Kodi centring
  a short list is accepted); the selected title stays dimly highlighted while the episodes (200)
  have focus. In 200 the selected row looks like the others while it isn't focused. The
  scrollbars (101, 201) are for mouse and touch only.
- **A PVR series' episodes are our own rows in 200, like every other title's.** Don't fill it
  from Kodi's `pvr://` listing (`<content>`): that loses hide-watched, our play and resume
  handling and some recordings, and needs a second list in every layout.
- **Switching must be as quick as Myth Estuary's.** Rows that can be made from what's already
  read (PVR series, Newest, rows kept from earlier in the session: `_at_hand`) show at once;
  only rows that need loading wait for `SETTLE`.
- No flicker while moving through titles ("Loading…" only after a delay) and no fade-ins: they
  make switching feel slow.
- The titles list shows no watched status.
- The picture's place is 16:9, so a `thumb` that's just the poster gives way to `landscape`,
  then `fanart` (`K.listitem_art()`). For PVR series it's the series fanart, not pvr.mythtv's
  preview image. With none, or one that won't load: `stage.jpg`, via the
  `script.centerstage.stage` Home property (a layout only finds images in its own skin
  folder's `media`).
- The background is `Skin.String(centerstage.background)` of the running skin, so nothing has
  to run at start-up (not a Home property). Myth Estuary sets it with its own background
  settings; its "Monthly background" clears it and reaches us only via `ColoredBackgroundImages`.
- **Kodi starts the PVR before the PVR add-on has connected** (pvr.mythtv takes a while), with
  no recordings, then gets them all at once. So "no recordings yet" means starting:
  `K.wait_for_pvr()` waits, once a session. Plugin listings wait (the skin's busy spinner
  shows); the window opens at once with a spinner and asks which Stage afterwards.
- Kodi tells add-ons nothing when recordings change: `_watch` re-reads them every
  `RECORDINGS_EVERY` and refreshes on a new `pvr.fingerprint()`.
- Disk space: `PVR.BackendDiskSpaceProgr` has no label form, so `_watch` bisects it with
  `Integer.IsGreater`; only reading the `PVR.BackendDiskSpace` label makes Kodi refresh it.
- The skin-facing hooks (`RunScript` arguments, `?action=stages`, widgets, the background
  string, per-skin layouts, `script.centerstage.deleting`) are documented in README
  "Integrating a skin"; keep it in step.

## Recording groups ("Stages")

- Users only ever see "Stage"; code, `group=` arguments and the `group` property say group.
- "All Stages" comes last in every Stage list (the question, "Stage…", `?action=stages`).
- Say "PVR", as Kodi does, never "DVR": in what users see and in the code.
- A recording's group is its JSON-RPC `directory` minus the title folder (`pvr.group_of()`).
  Recordings with no group folder (pvr.mythtv's "Show default recording group as root") are in
  `pvr.DEFAULT_GROUP` ("Default", which the user keeps), so `group=Default` works either way.
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
- **Newest** (`show_newest`): "<Stage> - Newest", always first, the newest shown recordings
  (counted after hiding watched ones), each prefixed with its series. `ref['titles']` holds the
  shown series, so hidden ones stay out and renames show.
- **Don't merge same-named titles**: each title's rows come from one place and its menu acts on
  one thing.
- A title's menu can override `hide_watched` for that title (`Store.hide_watched()`); Newest's
  override is its own, not its series'.
- Added seasons are named after the show; menus still say "Show - Season N" via
  `classify.season_description()`.

## Kodi facts this code relies on (checked in ../xbmc)

- **Module globals don't survive between invocations.** Every `RunScript`, plugin URL and
  context-menu click is a fresh interpreter. Persist in the profile, the settings, or a window
  property.
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
- **Don't use `doModal()` for it:** that ends only on `close()`, so leaving by a Home key would
  leave the script running. `show()` waits in `_until_left()`, which also ends once Home is
  active; calling `close()` then would move Kodi off Home.
- **Play with the `PlayMedia` builtin, not `Player.Open`.** `PlayMedia` asks whether to resume,
  as Kodi's windows do (add-on items too, on 21). `Player.Open` never asks, except for a
  `recordingid`, which asks and ignores `options`. `PlayMedia` reports no failure.
- **`Addon.openSettings()`** edits the calling `Addon` object's own settings, so `K.ADDON` is
  current afterwards.
- **"Open in …"** is `ActivateWindow(<window>,<path>,return)`; `return` makes Back at that path
  come back to ours, whose `onInit` refreshes. Myth Estuary's recordings window ignores the path.
- **Add-ons can't delete recordings** (no JSON-RPC method, builtin or `pvr://` file support), and
  Kodi's item context menu only opens for items Kodi listed itself, except in a list filled from
  `<content>` (`CDirectoryProvider::OnContextMenu`), which gets the key before Python's
  `onAction`. So a recording row's menu is Kodi's whole menu (the user's choice over filtering
  or merging it), opened by `window.RecordingMenu`, an invisible dialog (Default only) listing
  the recording's folder. Clear picks the entry labelled with Kodi's own "Delete" (string 117).
- Kodi lists a deleted recording until the PVR add-on reports it gone, so after a delete, or
  playing a recording (pvr.mythtv's "delete it?" at the end comes after our `onInit`),
  `_refresh_when_gone` checks `PVR.GetRecordingDetails` for a while.
- **Clear and Delete have no action in add-on windows** (keymaps map them per window), so they
  arrive as action 0; `window.DELETE_BUTTONS` matches their button codes.
- **`Container(id)` from Python, with no window context, resolves to the topmost dialog**, then
  the active window (`GUIInfoHelper::GetWindowWithCondition`).

## Not verified in a running Kodi yet

Only unit tests and stub-based smoke runs so far. Drop an item once the user confirms it works.
- Launching: where the add-on shows up; the context entry (plugin listings, recordings,
  Favourites, widgets); the widget click path (`PlayMedia` → `RunScript`); Myth Estuary's
  "Center Stage" home entry and Stages panel (its `Home.xml`).
- Add-on sources: `Files.GetDirectory`, `TVShowTitle`/`PluginCategory` and folder browsing in
  real add-ons (`../plugin.video.hoopla`, `../plugin.video.the-chosen`).
- Playback, resume points and the window coming back; "Open in …" from both menus and Back.
- Looks: all three layouts (Myth Estuary isn't installed in the Flatpak Kodi), the disk-space
  text, panel opacity, the spinner turning clockwise; Kodi 22.
- PVR: opening the window, Stages panel and widgets while pvr.mythtv is starting; a new
  recording appearing within a minute (Newest too); the Default group with "Show default
  recording group as root" on; the Movies and Newest titles.
- Kodi's menu on a recording: finding it in Kodi's listing, each entry (Play, Find similar,
  Information, Edit, pvr.mythtv's own), Clear picking Delete (from the user's remote; menu
  hidden on Myth Estuary), a recording in progress, and the lists updating afterwards and after
  pvr.mythtv's delete prompt at the end of playback.

# -*- coding: utf-8 -*-
"""The three-pane window: titles on the left; the selected title's episodes, or its seasons and
other folders to browse, top right; details of whatever is focused bottom right (that pane is
pure skin XML).

The top-right list is a small browser. Each title keeps a stack of the folders opened inside it
(remembered while the window is open). A ".." row and the Back key go up one level. Left arrow
always returns to the titles (the skin's onleft) without touching the stack, so right arrow comes
back to the same folder.

With more than one PVR recording group, show() first asks which group to show (the "ask_group"
setting). The window then lists that group's recordings plus the stored entries meant for it or
for every group, and Back on the titles returns to the question.
"""
import json
import threading
import time

import xbmc
import xbmcgui

import catalog
import kodiutil as K
from cache import EpisodeCache
from jsonrpc import RpcError
from model import ADDON, MOVIES, NEWEST, PVR, format_time, parent_row, pvr_key
from sources import addon, pvr
from store import Store

TITLES = 100
EPISODES = 200

ACTION_PREVIOUS_MENU = 10
ACTION_NAV_BACK = 92
ACTION_CONTEXT_MENU = 117
ACTION_DELETE_ITEM = 80   # from remote apps (Input.ExecuteAction "delete") or a user's keymap
# Clear and Delete have no action in add-on windows (Kodi's keymaps map them per window), so
# they arrive as action 0 with these button codes: XINPUT_IR_REMOTE_CLEAR (IR and CEC remotes)
# and KEY_VKEY | XBMCVK_DELETE (keyboard)
DELETE_BUTTONS = (249, 0xF087)

POLL = 0.03     # seconds between checks of the left list's selection
SETTLE = 0.1    # how long the selection must stay put before rows that need loading load
DISK_EVERY = 900   # seconds between asking Kodi to re-read the backend's disk space
DISK_WAIT = 30     # for this long after asking, read the answer every second (it comes later)
GONE_WAIT = 10     # after a delete is asked, for this long check whether the recording has gone

XML = 'script-centerstage-main.xml'
RECORDING_XML = 'script-centerstage-recording.xml'
RECORDING_LIST = 9100
RECORDINGS_PATH = 'script.centerstage.recordings'  # Home property: the folder that list shows
# Home property, set while Delete is picked from Kodi's context menu, so a skin can hide the menu
DELETING = 'script.centerstage.deleting'
MENU_BUTTONS = 1001   # Kodi's context menu: its first button (CGUIDialogContextMenu)


def level_key(entry_id, browse):
    return entry_id if browse is None else f'{entry_id}|{json.dumps(browse, sort_keys=True)}'


class MainWindow(xbmcgui.WindowXML):
    def onInit(self):
        if getattr(self, '_started', False):
            # back from playback (or a dialog): watched/resume state may have changed
            self._refresh(keep=True, reload_current=True)
            return
        self._started = True
        self.store = Store(K.PROFILE)
        self.cache = EpisodeCache(K.CACHE_DIR)
        self.rpc = K.rpc()
        self.major = K.kodi_major()
        self.lock = threading.RLock()
        self.closing = threading.Event()
        self.wake = threading.Event()
        self.rows = []
        self.recs = []
        self.episodes = []      # rows of the top-right list, ".." included
        self.mem = {}           # level_key -> rows, for this session
        self.stacks = {}        # entry id -> [(browse, label), ...] of opened folders
        self.current = None     # entry whose rows are (being) shown
        self.gen = 0            # bumps on every load; stale loads check it
        self.titles = self.getControl(TITLES)
        self.list = self.getControl(EPISODES)
        self.setProperty('group', K.group_label(self.group))  # under "Center Stage" at the top
        self._refresh(select=self.preselect)
        threading.Thread(target=self._watch, daemon=True).start()

    @property
    def shown_id(self):
        return self.current.id if self.current else None

    def _stack(self):
        return self.stacks.setdefault(self.current.id, []) if self.current else []

    # the left list

    def _refresh(self, keep=False, select=None, reload_current=False):
        was_at = self.titles.getSelectedPosition()
        if keep and select is None:
            # the row the user is on: the episodes shown can lag behind it while they scroll
            select = self.rows[was_at].id if 0 <= was_at < len(self.rows) else self.shown_id
        stored = self.store.entries()
        pvr_rows = []
        self.recs = []
        pvr_ok = False
        if K.setting_bool('include_pvr', True):
            try:
                self.recs = pvr.recordings(self.rpc)
                pvr_ok = True
            except RpcError as e:
                K.log(f'no PVR recordings: {e}')  # PVR disabled or not started yet
            self.recs = pvr.in_group(self.recs, self.group)
            pvr_rows = pvr.series_entries(self.recs, self.store.hidden_pvr(), self.store.renames())
        self.setProperty('pvr', 'true' if pvr_ok else '')
        rows = catalog.rows(stored, pvr_rows, K.setting_int('sort_order', catalog.SORT_TITLE),
                            self.group, K.movies_title(self.store), K.newest_title(self.group))
        with self.lock:
            self.rows = rows
            pos = next((n for n, e in enumerate(rows) if e.id == select), None)
            if pos is None:  # gone (e.g. its last recording was deleted): stay at the same place
                pos = min(max(was_at, 0), len(rows) - 1) if keep else 0
            self.titles.reset()
            self.titles.addItems([K.entry_listitem(e) for e in rows])
            self.setProperty('empty', '' if rows else 'true')
            if not rows:
                self.current = None
                self.setProperty('level', '')
                self._clear_episodes()
                return
            self.titles.selectItem(pos)
            if reload_current and rows[pos].id == self.shown_id:
                # library and PVR state is cheap to re-read; add-ons are re-read quietly
                for key in list(self.mem):
                    if not key.startswith(f'{ADDON}:'):
                        del self.mem[key]
                self.current = rows[pos]
                self._load(force=rows[pos].source != ADDON or self.major >= 22, quiet=True)
            elif rows[pos].id != self.shown_id or not keep:
                self._select(pos)
            else:
                self.current = rows[pos]  # same entry, possibly renamed
        if self.getFocusId() not in (TITLES, EPISODES):
            self.setFocusId(TITLES)

    def _watch(self):
        """WindowXML has no "selection changed" callback, so poll the left list."""
        seen, since, disk_next, disk_until, disk_at = None, 0.0, 0.0, 0.0, 0.0
        while not self.closing.is_set():
            self.wake.wait(POLL)
            self.wake.clear()
            if self.closing.is_set():
                break
            try:
                pos = self.titles.getSelectedPosition()
            except RuntimeError:
                break  # the window is gone
            now = time.monotonic()
            if now >= disk_next and self.getProperty('pvr'):
                # reading the label asks Kodi to re-read the backend's disk space (reading
                # PVR.BackendDiskSpaceProgr alone doesn't); the numbers arrive a little later
                xbmc.getInfoLabel('PVR.BackendDiskSpace')
                disk_next, disk_until = now + DISK_EVERY, now + DISK_WAIT
            if now < disk_until and now - disk_at >= 1:
                disk_at = now
                used = K.disk_used_percent()
                self.setProperty('diskspace', '' if used is None else K.tr('disk_used', used))
            if pos != seen:
                seen, since = pos, now
            with self.lock:
                # rows that are at hand switch at once; others wait until the selection settles,
                # so scrolling past titles doesn't load each one
                if 0 <= pos < len(self.rows) and self.rows[pos].id != self.shown_id \
                        and (now - since >= SETTLE or self._at_hand(self.rows[pos])):
                    self._select(pos)

    def _at_hand(self, entry):
        """Whether entry's rows show without loading: PVR series and Newest (made from the
        recordings already read) and rows kept from earlier in this session."""
        stack = self.stacks.get(entry.id)
        browse = stack[-1][0] if stack else None
        return entry.source in (PVR, NEWEST) or level_key(entry.id, browse) in self.mem

    # the top-right list

    def _select(self, pos, force=False, quiet=False):
        self.current = self.rows[pos]
        self._load(force=force, quiet=quiet)

    def _load(self, force=False, quiet=False, reselect=None):
        """Show the current entry's current level (its top level, or the folder last opened)."""
        entry = self.current
        stack = self._stack()
        browse = stack[-1][0] if stack else None
        key = level_key(entry.id, browse)
        self.gen += 1
        gen = self.gen
        self.setProperty('level', ' / '.join(label for _, label in stack))
        if entry.source == ADDON and entry.is_single:
            self._show(gen, entry, addon.rows(None, entry, self.major))
            return
        if entry.source in (PVR, NEWEST):
            # made from the recordings already read, so shown at once
            self._show(gen, entry, catalog.load_rows(self.rpc, entry, self.major, self.recs))
            return
        if not force:
            rows, stale = self.mem.get(key), False
            if rows is None and entry.source == ADDON:
                rows, age = self.cache.get(key)
                stale = rows is not None and age > 60 * K.setting_int('cache_minutes', 60)
            if rows is not None:
                self._show(gen, entry, rows, keep_position=quiet, reselect=reselect)
                if not stale:
                    return
                quiet = True
        if not quiet:
            self._clear_episodes(loading=True, parent=bool(stack))
        threading.Thread(target=self._fetch, args=(gen, entry, browse, key, quiet, reselect),
                         daemon=True).start()

    def _fetch(self, gen, entry, browse, key, quiet, reselect):
        try:
            rows = catalog.load_rows(self.rpc, entry, self.major, None, browse,
                                     K.tr('season_watched'))
        except Exception as e:  # an add-on can fail in any way; never take the window down
            K.log(f'loading {key} failed: {e}', xbmc.LOGWARNING)
            with self.lock:
                if gen == self.gen and not quiet:
                    self._clear_episodes(message=K.tr('load_failed', e),
                                         parent=bool(self._stack()))
            return
        with self.lock:
            self.mem[key] = rows
            if entry.source == ADDON:
                try:
                    self.cache.put(key, rows)
                except OSError as e:
                    K.log(f'caching {key} failed: {e}', xbmc.LOGWARNING)
            if not self.closing.is_set():
                self._show(gen, entry, rows, keep_position=quiet, reselect=reselect)

    def _show(self, gen, entry, rows, keep_position=False, reselect=None):
        with self.lock:
            if gen != self.gen:
                return
            if entry.source == ADDON:
                for row in rows:  # shown in the details where a recording shows its channel
                    row.origin = entry.origin
            episodic = not entry.is_single and entry.source != MOVIES
            # "Newest" is always newest first, whatever the episode order, and capped (after
            # hiding watched ones, so it's still full)
            arranged = catalog.arrange(
                rows, newest_first=episodic and entry.source != NEWEST
                and K.setting_int('episode_order', 0) == 1,
                hide_watched=episodic and K.setting_bool('hide_watched'),
                limit=pvr.NEWEST_LIMIT if entry.source == NEWEST else None)
            shown = ([parent_row()] if self._stack() else []) + arranged
            if keep_position:
                pos = self.list.getSelectedPosition()
            elif reselect is not None:
                # back out of a folder: land on that folder's row
                pos = next((n for n, r in enumerate(shown) if r.browse == reselect), 0)
            else:
                pos = 1 if shown and shown[0].parent and len(shown) > 1 else 0
            self.list.reset()
            self.list.addItems([K.episode_listitem(e) for e in shown])
            self.episodes = shown
            if 0 < pos < len(shown):
                self.list.selectItem(pos)
            self.setProperty('loading', '')
            self.setProperty('message', '' if arranged else K.tr('no_episodes'))

    def _clear_episodes(self, loading=False, message='', parent=False):
        self.list.reset()
        self.episodes = [parent_row()] if parent else []
        if parent:
            self.list.addItems([K.episode_listitem(self.episodes[0])])
        self.setProperty('loading', 'true' if loading else '')
        self.setProperty('message', message)

    def _down(self, row):
        with self.lock:
            self._stack().append((row.browse, row.label))
            self._load()

    def _up(self):
        with self.lock:
            stack = self._stack()
            if stack:
                browse, _ = stack.pop()
                self._load(reselect=browse)

    # input

    def onClick(self, control_id):
        if control_id == TITLES:
            with self.lock:
                pos = self.titles.getSelectedPosition()
                if 0 <= pos < len(self.rows) and self.rows[pos].id != self.shown_id:
                    self._select(pos)
            if self.list.size():
                self.setFocusId(EPISODES)
        elif control_id == EPISODES:
            pos = self.list.getSelectedPosition()
            if not 0 <= pos < len(self.episodes):
                return
            row = self.episodes[pos]
            if row.parent:
                self._up()
            elif row.is_folder:
                self._down(row)
            else:
                self._play(row)

    def onAction(self, action):
        aid = action.getId()
        if aid == ACTION_NAV_BACK and self.getFocusId() == EPISODES:
            if self._stack():
                self._up()
            else:
                self.setFocusId(TITLES)
        elif aid == ACTION_NAV_BACK and self.groups_asked:
            self._switch_group()
        elif aid in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK):
            self._close()
        elif aid == ACTION_CONTEXT_MENU:
            if self.getFocusId() == EPISODES:
                self._episode_menu()
            elif self.getFocusId() == TITLES:
                self._title_menu()
        elif self._is_delete(action) and self.getFocusId() == EPISODES:
            ep = self._focused_episode()
            if ep and ep.path:
                self._delete(ep)
        else:
            # navigation (including left from the episodes, which the skin sends to the titles)
            self.wake.set()

    @staticmethod
    def _is_delete(action):
        return (action.getId() == ACTION_DELETE_ITEM
                or (action.getId() == 0 and action.getButtonCode() in DELETE_BUTTONS))

    def _close(self):
        self.closing.set()
        self.wake.set()
        self.close()

    def _settings(self):
        """The add-on's settings, then everything they affect: panels, titles, episodes."""
        K.ADDON.openSettings()  # modal; it updates K.ADDON's own settings
        K.set_home_properties()
        self._refresh(keep=True, reload_current=True)

    def _switch_group(self):
        self.switch_group = True
        self._close()

    def _play(self, ep, resume=None):
        if resume is None and ep.resume > 0:
            choice = xbmcgui.Dialog().contextmenu(
                [K.tr('resume_from', format_time(ep.resume)), K.tr('from_start')])
            if choice < 0:
                return
            resume = choice == 0
        params = {'item': ep.play}
        if resume is not None:
            params['options'] = {'resume': resume}
        try:
            self.rpc.call('Player.Open', **params)
        except RpcError as e:
            K.log(f'playing {ep.play} failed: {e}', xbmc.LOGWARNING)
            K.notify(K.tr('play_failed'), xbmcgui.NOTIFICATION_ERROR)

    def _focused_episode(self):
        pos = self.list.getSelectedPosition()
        return self.episodes[pos] if 0 <= pos < len(self.episodes) else None

    def _delete(self, ep):
        """Delete a recording, which an add-on can only do through Kodi's own recording menu
        (only Kodi-filled lists get it): an invisible dialog lists the recording's folder, opens
        the menu on it and picks Delete, so Kodi asks "Delete this recording?" straight away."""
        home = xbmcgui.Window(10000)
        home.setProperty(RECORDINGS_PATH, ep.path.rsplit('/', 1)[0] + '?view=flat')
        home.setProperty(DELETING, 'true')
        dialog = RecordingDelete(RECORDING_XML, K.ADDON_PATH, 'Default', '1080i')
        dialog.path = ep.path
        dialog.outcome = None
        try:
            dialog.doModal()
            outcome = dialog.outcome
        finally:
            home.clearProperty(DELETING)
            del dialog
        if outcome == RecordingDelete.REFUSED:
            K.notify(K.tr('cant_delete'))
        elif outcome == RecordingDelete.ASKED:
            threading.Thread(target=self._refresh_when_gone, args=(ep.play['recordingid'],),
                             daemon=True).start()
        else:  # not in Kodi's listing: perhaps already gone
            self._refresh(keep=True, reload_current=True)

    def _refresh_when_gone(self, recording_id):
        """Kodi lists a deleted recording until the PVR add-on reports the change, a moment
        later: refresh once it has gone (after a No, it never does)."""
        monitor = xbmc.Monitor()
        end = time.monotonic() + GONE_WAIT
        while time.monotonic() < end and not self.closing.is_set():
            try:
                details = self.rpc.call('PVR.GetRecordingDetails', recordingid=recording_id,
                                        properties=['isdeleted'])
                gone = (details.get('recordingdetails') or {}).get('isdeleted')
            except RpcError:
                gone = True  # no such recording any more
            if gone:
                self._refresh(keep=True, reload_current=True)
                return
            if monitor.waitForAbort(0.5):
                return

    def _episode_menu(self):
        ep = self._focused_episode()
        actions = []
        if ep and not ep.is_folder and ep.resume > 0:
            actions.append((K.tr('from_start'), lambda: self._play(ep, resume=False)))
        actions.append((K.tr('refresh'), self._refresh_current))
        if ep and ep.path:
            actions.append((xbmc.getLocalizedString(117), lambda: self._delete(ep)))  # Delete
        movie = self.store.get(ep.entry_id) if ep and ep.entry_id else None
        if movie:
            # a movie in the "Movies" title, which has no row of its own to do this from
            if self.groups_asked or movie.group:
                actions.append((K.tr('set_group'), lambda: self._set_group(movie)))
            actions.append((K.tr('remove'), lambda: self._remove(movie)))
        self._menu(actions)

    def _title_menu(self):
        pos = self.titles.getSelectedPosition()
        if not 0 <= pos < len(self.rows):
            return
        entry = self.rows[pos]
        actions = []
        if entry.source != NEWEST:  # named after the group: nothing to rename, hide or remove
            actions.append((K.tr('rename'), lambda: self._rename(entry)))
        actions.append((K.tr('refresh'), self._refresh_current))
        if entry.source == PVR:
            actions.append((K.tr('hide_pvr'), lambda: self._hide(entry)))
        elif entry.source not in (MOVIES, NEWEST):  # movies are removed from their own rows' menu
            if self.groups_asked or entry.group:
                actions.append((K.tr('set_group'), lambda: self._set_group(entry)))
            actions.append((K.tr('remove'), lambda: self._remove(entry)))
        if self.store.hidden_pvr():
            actions.append((K.tr('show_hidden'), self._unhide))
        if self.groups_asked:
            actions.append((K.tr('switch_group'), self._switch_group))
        actions.append((K.tr('settings'), self._settings))
        self._menu(actions)

    @staticmethod
    def _menu(actions):
        choice = xbmcgui.Dialog().contextmenu([label for label, _ in actions])
        if choice >= 0:
            actions[choice][1]()

    def _refresh_current(self):
        with self.lock:
            if not self.current:
                return
            stack = self._stack()
            key = level_key(self.current.id, stack[-1][0] if stack else None)
            self.mem.pop(key, None)
            self.cache.drop(key)
            if self.current.source in (PVR, NEWEST):
                self._refresh(keep=True, reload_current=True)
            else:
                self._load(force=True)

    def _rename(self, entry):
        title = xbmcgui.Dialog().input(K.tr('rename'), entry.display_title)
        if title and title.strip() and title.strip() != entry.display_title:
            self.store.rename(entry.id, title.strip())
            self._refresh(keep=True)

    def _remove(self, entry):
        self.store.remove(entry.id)
        self.stacks.pop(entry.id, None)
        for key in [k for k in self.mem if k == entry.id or k.startswith(entry.id + '|')]:
            del self.mem[key]
        self.cache.drop(entry.id)
        self._refresh(keep=True, reload_current=self._in_movies(entry))

    def _set_group(self, entry):
        group = K.pick_entry_group(self.rpc, entry.group)
        if group is not None and group != entry.group:
            self.store.set_group(entry.id, group)
            self._refresh(keep=True, reload_current=self._in_movies(entry))

    def _in_movies(self, entry):
        """Whether entry is one of the movies in the "Movies" title being shown."""
        return bool(self.current and self.current.source == MOVIES
                    and any(m.id == entry.id for m in self.current.members))

    def _hide(self, entry):
        self.store.hide_pvr(pvr_key(entry.ref['title']), entry.display_title)
        self._refresh(keep=True)

    def _unhide(self):
        hidden = sorted(self.store.hidden_pvr().items(), key=lambda kv: kv[1].casefold())
        chosen = xbmcgui.Dialog().multiselect(K.tr('show_hidden'), [t for _, t in hidden])
        if not chosen:
            return
        for n in chosen:
            self.store.unhide_pvr(hidden[n][0])
        self._refresh(keep=True)


class RecordingDelete(xbmcgui.WindowXMLDialog):
    """Invisible: a Kodi-filled list of RECORDINGS_PATH (a list from <content> gets Kodi's
    own context menu, CDirectoryProvider::OnContextMenu). It opens that menu on the recording
    and picks Kodi's Delete. Set path before doModal; outcome says what happened."""
    ASKED = 'asked'        # Kodi asked "Delete this recording?" (the answer isn't known)
    REFUSED = 'refused'    # Kodi's menu has no Delete for it (e.g. still being recorded)
    MISSING = 'missing'    # not in Kodi's listing

    def onInit(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.outcome = self._pick_delete()
        finally:
            self.close()

    def _pick_delete(self):
        me = xbmcgui.getCurrentWindowDialogId()
        found = self._find(timeout=3.0)
        if found is None:
            K.log(f'{self.path} not found in Kodi\'s recordings listing')
            return self.MISSING
        self.getControl(RECORDING_LIST).selectItem(found)
        self._wait(lambda: self._info('CurrentItem') == str(found + 1), 1.0)
        xbmc.executebuiltin('Action(ContextMenu)')
        if not self._wait(lambda: xbmc.getCondVisibility('Window.IsActive(contextmenu)')
                          and xbmc.getInfoLabel(f'Control.GetLabel({MENU_BUTTONS})'), 2.0):
            K.log('Kodi\'s context menu didn\'t open on the recording')
            return self.MISSING
        # the menu is the topmost dialog, which Control.GetLabel reads with no window context;
        # Kodi labels its own Delete entry with its "Delete" string
        delete = xbmc.getLocalizedString(117)
        labels = []
        for button in range(MENU_BUTTONS, MENU_BUTTONS + 50):
            labels.append(xbmc.getInfoLabel(f'Control.GetLabel({button})'))
            if not labels[-1] or labels[-1] == delete:
                break
        if labels[-1] != delete:
            xbmc.executebuiltin('Action(Back)')
            return self.REFUSED
        xbmc.executebuiltin(f'SetFocus({MENU_BUTTONS + len(labels) - 1})')
        xbmc.executebuiltin('Action(Select)')
        # Kodi now closes the menu and asks; that (and deleting) is over when this dialog is on
        # top again and still is a moment later (it briefly is between the menu and the question)
        def on_top():
            return (xbmcgui.getCurrentWindowDialogId() == me
                    or not xbmc.getCondVisibility(f'Window.IsVisible({me})'))

        def settled():
            if not on_top():
                return False
            xbmc.sleep(200)
            return on_top()
        self._wait(lambda: not on_top(), 2.0)
        self._wait(settled, None)
        return self.ASKED

    def _info(self, name):
        return xbmc.getInfoLabel(f'Container({RECORDING_LIST}).{name}')

    def _find(self, timeout):
        """The recording's position in the list, once Kodi has filled it."""
        found = []

        def look():
            count = int(self._info('NumItems') or 0)
            found[:] = [n for n in range(count)
                        if self._info(f'ListItemAbsolute({n}).FileNameAndPath') == self.path][:1]
            return bool(found)
        self._wait(look, timeout)
        return found[0] if found else None

    @staticmethod
    def _wait(done, timeout):
        """Wait until done() (or timeout seconds; None for no limit, until Kodi exits)."""
        monitor = xbmc.Monitor()
        end = None if timeout is None else time.monotonic() + timeout
        while not done():
            if (end is not None and time.monotonic() > end) or monitor.waitForAbort(0.05):
                return False
        return True


def show(preselect=None, group=None, ask=True):
    """Open the window. Without a title or group to open on, first ask for a recording group
    (when there's more than one, the setting is on and ask isn't False), and again each time Back
    leaves the titles."""
    store = Store(K.PROFILE)
    groups = []
    if preselect is None and group is None and ask and K.setting_bool('ask_group', True):
        groups = K.recording_groups(K.rpc())
    ask = len(groups) > 1
    while True:
        if ask:
            ok, group = K.pick_group(K.tr('group'), groups + [None], store.last_group())
            if not ok:
                return
            store.set_last_group(group)
        K.set_home_properties()
        win = MainWindow(XML, K.ADDON_PATH, 'Default', '1080i')
        win.preselect = preselect
        win.group = group
        win.groups_asked = ask
        win.switch_group = False
        try:
            win.doModal()
            again = win.switch_group
        finally:
            if hasattr(win, 'closing'):
                win.closing.set()
                win.wake.set()
            del win
        if not again:
            return
        preselect = None

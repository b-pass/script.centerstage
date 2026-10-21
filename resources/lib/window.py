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
from model import ADDON, MOVIES, NEWEST, PVR, parent_row, pvr_key
from sources import addon, pvr
from store import Store

TITLES = 100
EPISODES = 200
EPISODES_GROUPS = (202, 203)  # groups holding 200, outermost first, in layouts that nest it

WINDOW_HOME = 10000

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
RECORDINGS_EVERY = 60   # seconds between re-reading the recordings, to notice new ones
WAIT_SLICE = 0.01  # seconds between show()'s checks; our callbacks wait for the next one
GONE_WAIT = 10     # after Kodi's menu on a recording or playing one, for this long (once no
                   # dialog is up) check whether it has gone

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
            if self.getProperty('starting'):
                return
            # back from playback (or a dialog): watched/resume state may have changed
            self._refresh(keep=True, reload_current=True)
            played, self.played = self.played, None
            if played is not None:  # pvr.mythtv may now ask whether to delete it
                threading.Thread(target=self._refresh_when_gone, args=(played,),
                                 daemon=True).start()
            return
        self._started = True
        self.played = None      # the recording last played from here
        self.store = Store(K.PROFILE)
        self.cache = EpisodeCache(K.CACHE_DIR)
        self.rpc = K.rpc()
        self.major = K.kodi_major()
        self.lock = threading.RLock()
        self.rows = []
        self.recs = []
        self.recs_key = None    # pvr.fingerprint() of all recordings, when last read
        self.episodes = []      # rows of the top-right list, ".." included
        self.mem = {}           # level_key -> rows, for this session
        self.stacks = {}        # entry id -> [(browse, label), ...] of opened folders
        self.current = None     # entry whose rows are (being) shown
        self.gen = 0            # bumps on every load; stale loads check it
        self.titles = self.getControl(TITLES)
        self.list = self.getControl(EPISODES)
        self.setProperty('group', K.group_label(self.group))  # under "Center Stage" at the top
        if self.starting:
            self.setProperty('starting', 'true')  # the layouts' spinner, in the titles' place
            threading.Thread(target=self._start_when_ready, daemon=True).start()
        else:
            self._start()

    def _start(self):
        self._refresh(select=self.preselect)
        threading.Thread(target=self._watch, daemon=True).start()

    def _start_when_ready(self):
        """The PVR is still starting: wait for its recordings, then ask which Stage if that's
        due, and show the titles."""
        K.wait_for_pvr(self.rpc, stop=self.closing)
        if self.closing.is_set():
            return
        if self.may_ask:
            groups = K.recording_groups(self.rpc)
            if len(groups) > 1:
                ok, group = K.pick_group(K.tr('group'), groups + [None], self.store.last_group())
                if not ok:
                    self._close()
                    return
                self.store.set_last_group(group)
                self.group, self.groups_asked = group, True
                self.setProperty('group', K.group_label(group))
        self.setProperty('starting', '')
        self._start()

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
        self.hide_watched = self.store.hide_watched()  # titles' own choices, kept for switching
        pvr_rows = []
        self.recs = []
        pvr_ok = False
        if K.setting_bool('include_pvr', True):
            try:
                self.recs = pvr.recordings(self.rpc)
                pvr_ok = True
            except RpcError as e:
                K.log(f'no PVR recordings: {e}')  # PVR disabled or not started yet
            self.recs_key = pvr.fingerprint(self.recs)
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
        recs_next = time.monotonic() + RECORDINGS_EVERY
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
            if now >= recs_next and pos == seen and now - since >= 1:  # not while scrolling
                recs_next = now + RECORDINGS_EVERY
                self._refresh_if_recordings_changed()
                continue
            if pos != seen:
                seen, since = pos, now
            with self.lock:
                # rows that are at hand switch at once; others wait until the selection settles,
                # so scrolling past titles doesn't load each one
                if 0 <= pos < len(self.rows) and self.rows[pos].id != self.shown_id \
                        and (now - since >= SETTLE or self._at_hand(self.rows[pos])):
                    self._select(pos)

    def _refresh_if_recordings_changed(self):
        """Kodi tells add-ons nothing when recordings change (one starts, finishes, is deleted
        or watched elsewhere), so _watch re-reads them now and then."""
        if self.recs_key is None or not K.setting_bool('include_pvr', True):
            return
        try:
            key = pvr.fingerprint(pvr.recordings(self.rpc))
        except RpcError:
            key = pvr.fingerprint([])
        if key != self.recs_key:
            shown = self.current
            self._refresh(keep=True, reload_current=bool(shown) and shown.source in (PVR, NEWEST))

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
                hide_watched=episodic and self._hides_watched(entry),
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

    def _hides_watched(self, entry):
        return self.hide_watched.get(entry.id, K.setting_bool('hide_watched'))

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
        """Kodi's PlayMedia, which asks whether to resume, as Kodi's own windows do, from the
        resume point Kodi keeps for the file (add-on items included); resume=False doesn't ask."""
        path = ep.play.get('file')
        if not path:
            K.log(f'nothing to play for {ep.play}', xbmc.LOGWARNING)
            K.notify(K.tr('play_failed'), xbmcgui.NOTIFICATION_ERROR)
            return
        option = '' if resume is None else ',resume' if resume else ',noresume'
        xbmc.executebuiltin(f'PlayMedia({K.builtin_param(path)}{option})')
        self.played = ep.play.get('recordingid')

    def _on_screen(self, control_id, groups):
        """A control's position and size: Python gives positions within the parent group, so
        add those of the groups (the ones the layout has)."""
        x = y = 0
        for group_id in groups:
            try:
                group = self.getControl(group_id)
            except RuntimeError:
                continue
            x, y = x + group.getX(), y + group.getY()
        control = self.getControl(control_id)
        return x + control.getX(), y + control.getY(), control.getWidth(), control.getHeight()

    def _focused_episode(self):
        pos = self.list.getSelectedPosition()
        return self.episodes[pos] if 0 <= pos < len(self.episodes) else None

    def _delete(self, ep):
        """Clear on a recording: Kodi asks "Delete this recording?" straight away."""
        self._recording_menu(ep, pick=xbmc.getLocalizedString(117))  # Delete

    def _recording_menu(self, ep, pick=None):
        """Kodi's own context menu on a recording, which only Kodi-filled lists get: an
        invisible dialog lists the recording's folder and opens the menu on it. With pick, the
        entry with that label is chosen for the user."""
        home = xbmcgui.Window(10000)
        home.setProperty(RECORDINGS_PATH, ep.path.rsplit('/', 1)[0] + '?view=flat')
        if pick:
            home.setProperty(DELETING, 'true')
        dialog = RecordingMenu(RECORDING_XML, K.ADDON_PATH, 'Default', '1080i')
        dialog.path = ep.path
        dialog.pick = pick
        dialog.rect = self._on_screen(EPISODES, EPISODES_GROUPS)
        dialog.outcome = None
        try:
            dialog.doModal()
            outcome = dialog.outcome
        finally:
            home.clearProperty(DELETING)
            del dialog
        if outcome == RecordingMenu.REFUSED:
            K.notify(K.tr('cant_delete'))
        elif outcome == RecordingMenu.DONE:
            if not pick:  # anything from marking it watched to renaming it
                self._refresh(keep=True, reload_current=True)
            threading.Thread(target=self._refresh_when_gone, args=(ep.play['recordingid'],),
                             daemon=True).start()
        else:  # not in Kodi's listing: perhaps already gone
            self._refresh(keep=True, reload_current=True)

    def _refresh_when_gone(self, recording_id):
        """Kodi lists a deleted recording until the PVR add-on reports the change, a moment
        later: refresh once it has gone (after a No, it never does). The wait starts again
        while a dialog is up, such as pvr.mythtv's "delete it?" after playback."""
        monitor = xbmc.Monitor()
        end = time.monotonic() + GONE_WAIT
        while time.monotonic() < end and not self.closing.is_set():
            if xbmc.getCondVisibility('System.HasActiveModalDialog'):
                end = time.monotonic() + GONE_WAIT
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
        if ep and ep.path:
            self._recording_menu(ep)
            return
        actions = []
        if ep and not ep.is_folder and ep.resume > 0:
            actions.append((K.tr('from_start'), lambda: self._play(ep, resume=False)))
        actions.append((K.tr('refresh'), self._refresh_current))
        stack = self._stack()
        actions += self._open_in_kodi(self.current, stack[-1][0] if stack else None)
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
        actions += self._open_in_kodi(entry)
        if not entry.is_single and entry.source != MOVIES:
            hides = self._hides_watched(entry)
            actions.append((K.tr('show_watched' if hides else 'hide_watched'),
                            lambda: self._set_hide_watched(entry, not hides)))
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

    def _open_in_kodi(self, entry, browse=None):
        """The menu line, if any, that opens what entry shows (at the browse level) in Kodi's
        own window: the add-on's, the library's or the recordings'. Back there returns here."""
        found = catalog.kodi_folder(entry, browse, self.recs) if entry else None
        if not found:
            return []
        window, path = found
        name = (xbmc.getLocalizedString(19017) if entry.source == PVR  # Recordings
                else entry.origin if entry.source == ADDON and entry.origin
                else xbmc.getLocalizedString(3))  # Videos
        return [(K.tr('open_in', name), lambda: xbmc.executebuiltin(
            f'ActivateWindow({window},{K.builtin_param(path)},return)'))]

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

    def _set_hide_watched(self, entry, hide):
        self.store.set_hide_watched(entry.id, hide, K.setting_bool('hide_watched'))
        with self.lock:
            self.hide_watched = self.store.hide_watched()
            if self.current and self.current.id == entry.id:
                self._load()

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


class RecordingMenu(xbmcgui.WindowXMLDialog):
    """Invisible: a Kodi-filled list of RECORDINGS_PATH (a list from <content> gets Kodi's
    own context menu, CDirectoryProvider::OnContextMenu). It opens that menu on the recording
    and leaves it to the user, or picks the entry labelled pick. Set path, pick and rect (where
    the menu should centre) before doModal; outcome says what happened."""
    DONE = 'done'          # the menu opened, and whatever was chosen from it has finished
    REFUSED = 'refused'    # Kodi's menu has no pick entry (e.g. no Delete while recording)
    MISSING = 'missing'    # not in Kodi's listing

    def onInit(self):
        # Kodi's menu centres on the focused control: lay the list where ours is
        x, y, width, height = self.rect
        recordings = self.getControl(RECORDING_LIST)
        recordings.setPosition(x, y)
        recordings.setWidth(width)
        recordings.setHeight(height)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.outcome = self._menu()
        finally:
            self.close()

    def _menu(self):
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
        if self.pick:
            # the menu is the topmost dialog, which Control.GetLabel reads with no window
            # context; Kodi labels its entries with its own strings (Delete: "Delete")
            labels = []
            for button in range(MENU_BUTTONS, MENU_BUTTONS + 50):
                labels.append(xbmc.getInfoLabel(f'Control.GetLabel({button})'))
                if not labels[-1] or labels[-1] == self.pick:
                    break
            if labels[-1] != self.pick:
                xbmc.executebuiltin('Action(Back)')
                return self.REFUSED
            xbmc.executebuiltin(f'SetFocus({MENU_BUTTONS + len(labels) - 1})')
            xbmc.executebuiltin('Action(Select)')
        # Kodi closes the menu and runs the entry; that's over when this dialog is on top again
        # and still is a moment later (it briefly is between the menu and, say, a question)
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
        return self.DONE

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
    may_ask = preselect is None and group is None and ask and K.setting_bool('ask_group', True)
    # while the PVR starts, the window opens at once and waits for it (asking afterwards)
    starting = K.pvr_starting(K.rpc())
    while True:
        asked = False
        if may_ask and not starting:
            groups = K.recording_groups(K.rpc())
            asked = len(groups) > 1
            if asked:
                ok, group = K.pick_group(K.tr('group'), groups + [None], store.last_group())
                if not ok:
                    return
                store.set_last_group(group)
        K.set_home_properties()
        win = MainWindow(XML, K.ADDON_PATH, 'Default', '1080i')
        win.preselect = preselect
        win.group = group
        win.groups_asked = asked
        win.starting = starting
        win.may_ask = may_ask
        win.switch_group = False
        win.closing = threading.Event()
        win.wake = threading.Event()
        try:
            win.show()
            _until_left(win)
            again = win.switch_group
        finally:
            win.closing.set()
            win.wake.set()
            del win
        if not again:
            return
        preselect = None
        starting = False


def _until_left(win):
    """doModal() without its catch: that ends only on close(), but Kodi can leave the window
    another way (a Home key, the skin's menu), and activating Home drops it from Kodi's history,
    so nothing returns to it. Calling close() then would send Kodi to the previous window, off
    Home, so this just stops waiting. The callbacks run while waitForAbort waits."""
    monitor = xbmc.Monitor()
    while not win.closing.is_set() and xbmcgui.getCurrentWindowId() != WINDOW_HOME:
        if monitor.waitForAbort(WAIT_SLICE):
            return

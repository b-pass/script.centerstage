# -*- coding: utf-8 -*-
"""plugin://script.centerstage/ : the title list as an ordinary folder, for home-screen widgets.

  /                 open the window; loaded as a widget (Home is the active window): the titles
  /?action=list     the titles (use this path for a widget); &group=<name> for one recording
                    group's titles
  /?action=open&id= open the window on that title (&group= as above)
  /?action=stages   the Stages (recording groups), "All groups" first, for a skin's home menu.
                    Each item's "stage" property holds the RunScript arguments that open it
                    without asking for a group: RunScript(script.centerstage,<stage>)
"""
import os
import sys
from urllib.parse import parse_qsl, urlencode

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'lib'))

import xbmc  # noqa: E402
import xbmcgui  # noqa: E402
import xbmcplugin  # noqa: E402

import catalog  # noqa: E402
import kodiutil as K  # noqa: E402
from jsonrpc import RpcError  # noqa: E402
from model import plain  # noqa: E402
from sources import pvr  # noqa: E402
from store import Store  # noqa: E402

BASE = f'plugin://{K.ADDON_ID}/'


def url(**params):
    return BASE + '?' + urlencode(params)


def group_params(group):
    return {} if group is None else {'group': group}


def script_args(entry_id=None, group=None, ask=True):
    # urlencoded, so ids (which may be add-on URLs) can't contain the commas and quotes that
    # builtin parameter parsing splits on
    params = dict({'id': entry_id} if entry_id else {}, **group_params(group))
    if not ask:
        params['ask'] = '0'
    return urlencode(params)


def open_window(entry_id=None, group=None, ask=True):
    args = script_args(entry_id, group, ask)
    xbmc.executebuiltin(f'RunScript({K.ADDON_ID}{"," + args if args else ""})')


def all_rows(group=None):
    store = Store(K.PROFILE)
    pvr_rows = []
    if K.setting_bool('include_pvr', True):
        try:
            recs = pvr.in_group(pvr.recordings(K.rpc()), group)
            pvr_rows = pvr.series_entries(recs, store.hidden_pvr(), store.renames())
        except RpcError as e:
            K.log(f'no PVR recordings: {e}')
    return catalog.rows(store.entries(), pvr_rows, K.setting_int('sort_order', catalog.SORT_TITLE),
                        group, K.movies_title(store), K.newest_title(group))


def title_item(entry, group):
    # Label and art only: an item with a video info tag would go through the user's "select
    # action" (e.g. show information) when clicked in a widget instead of opening our window.
    li = xbmcgui.ListItem(plain(entry.display_title), offscreen=True)
    li.setArt(K.title_art(entry))
    li.setProperty('IsPlayable', 'false')
    return url(action='open', id=entry.id, **group_params(group)), li, False


def list_titles(handle, group=None):
    items = [title_item(e, group) for e in all_rows(group)]
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.setContent(handle, 'videos')
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


def list_stages(handle):
    items = []
    for group in [None] + K.recording_groups(K.rpc()):
        li = xbmcgui.ListItem(K.group_label(group), offscreen=True)
        li.setProperty('stage', script_args(group=group, ask=False))
        li.setProperty('IsPlayable', 'false')
        items.append((url(action='open', **group_params(group), ask='0'), li, False))
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.endOfDirectory(handle, cacheToDisc=False)


def main(argv):
    handle = int(argv[1]) if len(argv) > 1 and argv[1].lstrip('-').isdigit() else -1
    params = dict(parse_qsl(argv[2].lstrip('?'), keep_blank_values=True)) if len(argv) > 2 else {}
    action = params.get('action')
    group = params.get('group')
    if action == 'open' or (action is None and handle < 0):
        open_window(params.get('id'), group, params.get('ask') != '0')
        if handle >= 0:
            # reached through PlayMedia (a widget click): tell Kodi there's nothing to play
            xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
    elif action == 'stages':
        list_stages(handle)
    elif action == 'list' or xbmc.getCondVisibility('Window.IsActive(home)'):
        # a widget: opening the plugin from anywhere else activates the Videos window first
        # (GUIWindowManager adds it to the history before WINDOW_INIT), so Home isn't active then
        list_titles(handle, group)
    else:
        open_window()
        xbmcplugin.endOfDirectory(handle, succeeded=False)


if __name__ == '__main__':
    main(sys.argv)

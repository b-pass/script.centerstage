# -*- coding: utf-8 -*-
"""The "Center Stage…" context menu entry: add (or remove) whatever it was opened on."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'lib'))

import xbmc  # noqa: E402
import xbmcaddon  # noqa: E402
import xbmcgui  # noqa: E402

import classify  # noqa: E402
import kodiutil as K  # noqa: E402
from jsonrpc import RpcError  # noqa: E402
from model import SEASON, ADDON, pvr_key  # noqa: E402
from sources import addon, library  # noqa: E402
from store import Store  # noqa: E402

ART_KEYS = ('thumb', 'poster', 'fanart', 'landscape', 'banner', 'clearlogo', 'icon',
            'tvshow.poster', 'tvshow.fanart', 'tvshow.banner', 'tvshow.clearlogo',
            'tvshow.landscape', 'season.poster', 'season.fanart', 'season.banner',
            'season.landscape')

VERB_LABELS = {classify.ADD_SHOW: 'add_show', classify.ADD_SEASON: 'add_season',
               classify.ADD_MOVIE: 'add_movie', classify.ADD_FOLDER: 'add_folder'}


def addon_name(path):
    if not path.startswith('plugin://'):
        return ''
    addon_id = path[len('plugin://'):].split('/', 1)[0].split('?', 1)[0]
    try:
        return xbmcaddon.Addon(addon_id).getAddonInfo('name')
    except RuntimeError:
        return addon_id


def snapshot(li, rpc):
    tag = li.getVideoInfoTag()
    art = {k: li.getArt(k) for k in ART_KEYS}
    snap = classify.Snapshot(
        label=li.getLabel(), path=li.getPath(), is_folder=li.isFolder(),
        media_type=tag.getMediaType(), dbid=tag.getDbId(), title=tag.getTitle(),
        tvshowtitle=tag.getTVShowTitle(), season=tag.getSeason(), episode=tag.getEpisode(),
        plot=tag.getPlot(), year=tag.getYear(), art={k: v for k, v in art.items() if v},
        parent_path=li.getProperty('ParentPath') or xbmc.getInfoLabel('Container.FolderPath'),
        plugin_category=xbmc.getInfoLabel('Container.PluginCategory'))
    snap.addon_name = addon_name(snap.path)
    if classify.is_library(snap) and snap.media_type in ('season', 'episode'):
        lookup = library.season_parent if snap.media_type == 'season' else library.episode_parent
        try:
            snap.tvshowid, season, show = lookup(rpc, snap.dbid)
            snap.season = season if season >= 0 else snap.season
            snap.tvshowtitle = snap.tvshowtitle or show
        except (RpcError, KeyError) as e:
            K.log(f'library lookup for {snap.media_type} {snap.dbid} failed: {e}',
                  xbmc.LOGWARNING)
    return snap


def menu_label(cand, stored_ids):
    e = cand.entry
    title = e.display_title or e.season_label or '…'
    if e.id in stored_ids:
        return K.tr('remove_named', title)
    if cand.verb == classify.ADD_ITEM:
        return K.tr('add_episode' if e.show_title else 'add_item', title)
    return K.tr(VERB_LABELS[cand.verb], title)


def busy(on):
    xbmc.executebuiltin('ActivateWindow(busydialognocancel)' if on
                        else 'Dialog.Close(busydialognocancel)')


def name_it(cand, snap, rpc):
    """Find the show name (or ask for it), then let the user confirm the title. False = cancelled."""
    e = cand.entry
    if cand.needs_show_name:
        busy(True)
        try:
            peek = snap.path if snap.is_folder else e.ref['path']
            show = addon.peek_show_title(rpc, peek, K.kodi_major())
        except RpcError as err:
            K.log(f'looking for a show title in {peek} failed: {err}', xbmc.LOGWARNING)
            show = ''
        finally:
            busy(False)
        if not show:
            heading = K.tr('show_name') if e.kind == SEASON else K.tr('folder_name')
            show = xbmcgui.Dialog().input(heading).strip()
            if not show:
                return False
            classify.with_show_name(cand, show)
            return True
        classify.with_show_name(cand, show)
    if e.source == ADDON and cand.verb in (classify.ADD_SEASON, classify.ADD_FOLDER):
        title = xbmcgui.Dialog().input(K.tr('confirm_name'), e.display_title).strip()
        if not title:
            return False
        e.display_title = title
    return True


def pvr_menu(snap, store):
    title = classify.pvr_title(snap)
    key = pvr_key(title)
    hidden = store.hidden_pvr()
    if key in hidden:
        if xbmcgui.Dialog().contextmenu([K.tr('unhide_named', hidden[key])]) == 0:
            store.unhide_pvr(key)
            K.notify(K.tr('added'))
    else:
        K.notify(K.tr('pvr_already', title))


def main():
    li = getattr(sys, 'listitem', None)
    if li is None:
        return
    rpc = K.rpc()
    store = Store(K.PROFILE)
    snap = snapshot(li, rpc)
    if classify.is_pvr_recording(snap):
        pvr_menu(snap, store)
        return
    cands = classify.candidates(snap)
    if not cands:
        K.notify(K.tr('nothing'))
        return
    stored_ids = {e.id for e in store.entries()}
    choice = xbmcgui.Dialog().contextmenu([menu_label(c, stored_ids) for c in cands])
    if choice < 0:
        return
    cand = cands[choice]
    if cand.entry.id in stored_ids:
        store.remove(cand.entry.id)
        K.notify(K.tr('removed'))
        return
    if not name_it(cand, snap, rpc):
        return
    last = store.last_group()
    group = K.pick_entry_group(rpc, last or '')
    if group is None:
        return
    cand.entry.group = group
    K.notify(K.tr('added') if store.add(cand.entry) else K.tr('already'))


if __name__ == '__main__':
    main()

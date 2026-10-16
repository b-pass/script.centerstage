# -*- coding: utf-8 -*-
"""Everything that touches Kodi's Python modules, shared by the window, the context menu and the
widget listing."""
import os
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from jsonrpc import Rpc, RpcError
from model import (LIBRARY, MOVIES, MOVIES_ID, NEWEST, PVR, details_code, episode_code,
                   format_time, parse_date, plain)
from sources import pvr

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_PATH = ADDON.getAddonInfo('path')
# the empty stage (tools/art.py), for titles with no picture of their own
STAGE_ART = os.path.join(ADDON_PATH, 'resources', 'stage.jpg')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
CACHE_DIR = os.path.join(PROFILE, 'cache')

# strings.po ids
S = {
    'add_show': 32002, 'add_season': 32003, 'add_movie': 32004, 'add_episode': 32005,
    'add_folder': 32006, 'add_item': 32039, 'remove_named': 32007, 'added': 32008,
    'already': 32009, 'removed': 32010, 'show_name': 32011, 'confirm_name': 32012,
    'pvr_already': 32013, 'unhide_named': 32014, 'nothing': 32015, 'folder_name': 32038,
    'resume_from': 32020, 'from_start': 32021, 'remove': 32022, 'rename': 32023,
    'refresh': 32024, 'hide_pvr': 32025, 'show_hidden': 32026,
    'loading': 32028, 'empty': 32029, 'load_failed': 32030, 'no_episodes': 32031,
    'library': 32032, 'dvr': 32033, 'watched': 32034, 'left': 32035, 'recordings': 32036,
    'play_failed': 32040, 'one_recording': 32041, 'season_watched': 32042,
    'season_episode': 32043, 'episode_n': 32044, 'group': 32045, 'all_groups': 32046,
    'which_group': 32048, 'set_group': 32049, 'switch_group': 32050, 'movies': 32051,
    'one_movie': 32052, 'n_movies': 32053, 'disk_used': 32054, 'newest': 32055,
    'check_updates': 32056, 'checking_updates': 32057, 'settings': 32058,
}


def tr(key, *args):
    text = ADDON.getLocalizedString(S[key])
    return text.format(*args) if args else text


def log(txt, level=xbmc.LOGINFO):
    xbmc.log(f'{ADDON_ID}: {txt}', level=level)


def notify(msg, icon=xbmcgui.NOTIFICATION_INFO):
    xbmcgui.Dialog().notification(ADDON_NAME, msg, icon, 3000)


def disk_used_percent():
    """How full the DVR backend's disk is, 0-100, or None when it isn't reported.

    PVR.BackendDiskSpaceProgr is a number with no label form ($INFO and getInfoLabel give
    nothing), so it is found by bisecting with Integer.IsGreater. It is 255 when unreported."""
    info = 'PVR.BackendDiskSpaceProgr'
    if xbmc.getCondVisibility(f'Integer.IsGreater({info},100)'):
        return None
    low, high = 0, 100
    while low < high:
        mid = (low + high) // 2
        if xbmc.getCondVisibility(f'Integer.IsGreater({info},{mid})'):
            low = mid + 1
        else:
            high = mid
    return low


def kodi_major():
    try:
        return int(xbmc.getInfoLabel('System.BuildVersion').split('.')[0])
    except ValueError:
        return 0


def rpc():
    return Rpc(xbmc.executeJSONRPC)


def setting_int(key, default=0):
    try:
        return ADDON.getSettings().getInt(key)
    except (RuntimeError, TypeError, AttributeError):
        return default


def setting_bool(key, default=False):
    try:
        return ADDON.getSettings().getBool(key)
    except (RuntimeError, TypeError, AttributeError):
        return default


def recording_groups(rpc):
    """The DVR's recording groups (Default first), or [] with the DVR off."""
    if not setting_bool('include_dvr', True):
        return []
    try:
        return pvr.groups(pvr.recordings(rpc))
    except RpcError as e:
        log(f'no PVR recordings: {e}')
        return []


def movies_title(store):
    """The "Movies" title's name (it can be renamed), or None when movies aren't grouped."""
    if not setting_bool('group_movies', True):
        return None
    return store.renames().get(MOVIES_ID) or tr('movies')


def set_panel_colours():
    """The panels' colours, from the panel_opacity setting, as Home window properties:
    script.centerstage.panel tints Estuary's panel texture, script.centerstage.panel_dark is the
    Default layout's flat colour. (On Home because a texture's colour is read with no window
    context, so a property of our own window might not be found.)"""
    pct = min(100, max(0, setting_int('panel_opacity', 80)))
    alpha = f'{round(pct * 255 / 100):02X}'
    home = xbmcgui.Window(10000)
    home.setProperty(f'{ADDON_ID}.panel', alpha + 'FFFFFF')
    home.setProperty(f'{ADDON_ID}.panel_dark', alpha + '181C22')


def newest_title(group):
    """The "Newest" title's name, "<group> - Newest", or None when it's turned off."""
    if not (setting_bool('include_dvr', True) and setting_bool('show_newest', True)):
        return None
    return tr('newest', group_label(group))


def group_label(group):
    """None is every group."""
    return tr('all_groups') if group is None else group


def pick_group(heading, options, current=None):
    """A choice from options (None and group names). Returns (False, None) if cancelled."""
    pre = options.index(current) if current in options else 0
    n = xbmcgui.Dialog().select(heading, [group_label(g) for g in options], preselect=pre)
    return (True, options[n]) if n >= 0 else (False, None)


def pick_entry_group(rpc, current=''):
    """Which group a stored entry is shown in: "" for all of them. None if cancelled; "" without
    asking when there's only one group."""
    named = recording_groups(rpc)
    if len(named) < 2 and current in named + ['']:
        return ''
    options = [None] + sorted(set(named) | ({current} - {''}),
                              key=lambda g: (g != pvr.DEFAULT_GROUP, g.casefold()))
    ok, group = pick_group(tr('which_group'), options, current or None)
    return (group or '') if ok else None


def origin_label(entry):
    """Where an entry comes from, for the details pane."""
    if entry.source == LIBRARY:
        return tr('library')
    if entry.source == MOVIES:
        n = len(entry.members)
        return tr('one_movie') if n == 1 else tr('n_movies', n)
    if entry.source == NEWEST:
        return tr('dvr') + '[CR]' + (tr('one_recording') if entry.count == 1
                                     else tr('recordings', entry.count))
    if entry.source == PVR:
        # "DVR - BBC One[CR]12 recordings"
        text = tr('dvr') + (' - ' + entry.origin if entry.origin else '')
        if entry.count:
            text += '[CR]' + (tr('one_recording') if entry.count == 1
                              else tr('recordings', entry.count))
        return text
    return entry.origin


def listitem_art(art):
    art = dict(art)
    poster = art.get('poster') or art.get('tvshow.poster') or art.get('season.poster')
    thumb = art.get('thumb') or art.get('landscape') or art.get('icon')
    if not poster:
        poster = thumb
    if not thumb:
        thumb = art.get('fanart') or poster
    art['poster'] = poster or ''
    art['thumb'] = thumb or ''
    art.setdefault('fanart', art.get('tvshow.fanart') or '')
    return {k: v for k, v in art.items() if v}


def title_art(entry):
    """A title's art; the empty stage when it has no picture."""
    art = listitem_art(entry.art)
    if not art.get('thumb'):
        art['thumb'] = STAGE_ART
    return art


def entry_listitem(entry, path=''):
    title = plain(entry.display_title)  # titles are never coloured, whatever the source sent
    li = xbmcgui.ListItem(title, offscreen=True)
    li.setArt(title_art(entry))
    tag = li.getVideoInfoTag()
    tag.setTitle(title)
    tag.setPlot(entry.plot)
    if entry.year:
        tag.setYear(entry.year)
    tag.setMediaType('movie' if entry.kind == 'movie' else 'tvshow')
    li.setProperty('entry_id', entry.id)
    li.setProperty('origin', origin_label(entry))
    if path:
        li.setPath(path)
    return li


def _strftime(fmt, when):
    try:
        return time.strftime(fmt, when)
    except ValueError:
        return ''


def _date_time(text, region):
    """An Episode.date as (date in the user's format for region, "dateshort" or "datelong";
    time without seconds, or '' when it has none)."""
    parsed = parse_date(text)
    if not parsed:
        return '', ''
    when, has_time = parsed
    clock = _strftime(xbmc.getRegion('time').replace(':%S', ''), when) if has_time else ''
    return _strftime(xbmc.getRegion(region), when), clock


def short_date(text):
    """For the episode list: the date, and the time when it has one (recordings)."""
    return '  '.join(p for p in _date_time(text, 'dateshort') if p)


def episode_status(ep):
    """Length, then watched or the time left."""
    parts = []
    length = ep.runtime or int(ep.total)
    if length:
        parts.append(format_time(length))
    if ep.playcount > 0:
        parts.append(tr('watched'))
    elif ep.resume > 0 and ep.total > ep.resume:
        parts.append(tr('left', format_time(ep.total - ep.resume)))
    return ' · '.join(parts)


def episode_details(ep):
    """The grey lines at the top right of the details pane: the channel; the date; then the
    time, length and watched state. (Date and time on one line wrapped badly.)"""
    if ep.is_folder:
        return ep.label2
    day, clock = _date_time(ep.date, 'datelong')
    last = ' · '.join(p for p in (clock, episode_status(ep)) if p)
    return '[CR]'.join(p for p in (ep.channel, day, last) if p)


def episode_label(ep):
    """"Season 1, Episode 2" for an episode with no name of its own, else its label; after
    "Series · " in the "Newest" title, where the series are mixed."""
    label = ep.label
    if ep.untitled and not ep.is_folder and ep.episode > 0:
        if ep.season >= 0:
            label = tr('season_episode', ep.season, ep.episode)
        else:
            label = tr('episode_n', ep.episode)
    return f'{ep.show} · {label}' if ep.show else label


def details_name(ep):
    """The episode's name in the details pane: "S1 E02 · Name" (the row has just the name), and
    never coloured (only the row keeps pvr.mythtv's colour for damaged recordings)."""
    name = plain(episode_label(ep))
    code = '' if ep.untitled or ep.is_folder else details_code(ep.season, ep.episode)
    if not code:
        return name
    return code if name == episode_code(ep.season, ep.episode) else f'{code} · {name}'


def episode_listitem(ep):
    li = xbmcgui.ListItem(episode_label(ep), ep.label2 if ep.is_folder else short_date(ep.date),
                          offscreen=True)
    li.setProperty('name', details_name(ep))
    if ep.parent:
        li.setIsFolder(True)
        li.setProperty('parent', 'true')
        return li
    li.setArt(listitem_art(ep.art))
    li.setIsFolder(ep.is_folder)
    tag = li.getVideoInfoTag()
    tag.setTitle(plain(ep.title or ep.label))
    tag.setPlot(ep.plot)
    if ep.media_type:
        tag.setMediaType(ep.media_type)
    if ep.season >= 0:
        tag.setSeason(ep.season)
    if ep.episode >= 0:
        tag.setEpisode(ep.episode)
    tag.setPlaycount(ep.playcount)
    if ep.runtime:
        tag.setDuration(ep.runtime)
    if ep.resume > 0 and ep.total > 0:
        tag.setResumePoint(ep.resume, ep.total)
    if ep.date:
        tag.setFirstAired(ep.date[:10])
    li.setProperty('details', episode_details(ep))
    li.setProperty('watched', 'true' if ep.playcount > 0 else '')
    return li

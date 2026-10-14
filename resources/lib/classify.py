# -*- coding: utf-8 -*-
"""Turns what the context menu was opened on into candidate entries. Kodi-free.

context.py copies everything it needs out of sys.listitem and a few Container.* infolabels into a
Snapshot (plus a JSON-RPC lookup for library seasons and episodes), then calls candidates().
"""
from dataclasses import dataclass, field
import re

from model import (Entry, LIBRARY, ADDON, SHOW, SEASON, MOVIE, ITEM, entry_id, plain,
                   episode_code)

# verbs, one per kind of menu line context.py shows
ADD_SHOW = 'show'
ADD_SEASON = 'season'
ADD_MOVIE = 'movie'
ADD_ITEM = 'item'
ADD_FOLDER = 'folder'   # an add-on folder we can't tell is a show or a season

_SEASON_RE = re.compile(
    r'^\s*(?:(?:season|series|staffel|saison|temporada|stagione|seizoen|s)\s*\.?\s*\d+\b.*'
    r'|specials?|extras)\s*$',
    re.IGNORECASE)

LIBRARY_TYPES = ('movie', 'tvshow', 'season', 'episode')


@dataclass
class Snapshot:
    label: str = ''
    path: str = ''
    is_folder: bool = False
    media_type: str = ''
    dbid: int = -1
    title: str = ''
    tvshowtitle: str = ''
    season: int = -1
    episode: int = -1
    plot: str = ''
    year: int = 0
    art: dict = field(default_factory=dict)
    parent_path: str = ''       # the folder the item was listed in
    plugin_category: str = ''   # Container.PluginCategory of that folder, if the add-on set one
    addon_name: str = ''        # name of the add-on that owns path, if it's a plugin:// path
    tvshowid: int = -1          # filled in by context.py for library seasons and episodes


@dataclass
class Candidate:
    verb: str
    entry: Entry
    needs_show_name: bool = False   # context.py must find (or ask for) entry.show_title


def is_season_label(text):
    return bool(text) and bool(_SEASON_RE.match(text))


def is_pvr_recording(snap):
    return snap.path.startswith('pvr://recordings')


def is_library(snap):
    return (not snap.path.startswith('plugin://') and snap.dbid > 0
            and snap.media_type in LIBRARY_TYPES)


def pvr_title(snap):
    # the recordings window shows pvr.mythtv's damaged recordings as [COLOR yellow]Title[/COLOR]
    return ' '.join(plain(snap.title or snap.label).split())


def season_label(snap):
    if is_season_label(snap.label):
        return snap.label.strip()
    if snap.season == 0:
        return 'Specials'
    if snap.season > 0:
        return f'Season {snap.season}'
    return snap.label.strip()


def season_title(show, season):
    return f'{show} - {season}' if show else season


def resolve_show_name(snap, *not_names):
    """Show name from the item itself, then from the folder's plugin category.

    Returns '' when neither is usable; context.py then tries an episode inside the folder, and
    finally asks the user.
    """
    if snap.tvshowtitle.strip():
        return snap.tvshowtitle.strip()
    category = snap.plugin_category.strip()
    rejected = {n.strip().casefold() for n in (snap.addon_name, snap.label) + not_names if n}
    if category and category.casefold() not in rejected and not is_season_label(category):
        return category
    return ''


def show_art(art):
    """Art for a row that stands for a whole show, preferring the show's own images."""
    out = dict(art)
    for key in ('poster', 'fanart', 'banner', 'clearlogo', 'landscape', 'thumb'):
        if art.get(f'tvshow.{key}'):
            out[key] = art[f'tvshow.{key}']
    return out


def season_art(art):
    out = show_art(art)
    for key in ('poster', 'fanart', 'banner', 'landscape', 'thumb'):
        if art.get(f'season.{key}'):
            out[key] = art[f'season.{key}']
    return out


def _make(source, kind, ref, display_title, snap, **kw):
    return Entry(id=entry_id(source, kind, ref), source=source, kind=kind, ref=ref,
                 display_title=display_title, plot=kw.pop('plot', snap.plot),
                 year=kw.pop('year', snap.year), art=kw.pop('art', dict(snap.art)), **kw)


def _item_title(snap):
    title = snap.title or snap.label
    code = episode_code(snap.season, snap.episode)
    if code and code not in title:
        title = f'{code} {title}'
    return f'{snap.tvshowtitle} - {title}' if snap.tvshowtitle else title


def candidates(snap):
    """Everything the user could add from this item, most specific first."""
    if is_pvr_recording(snap):
        return []
    if is_library(snap):
        return _library(snap)
    return _addon(snap)


def _library(snap):
    mt = snap.media_type
    show = snap.tvshowtitle or (snap.title if mt == 'tvshow' else '') or snap.label
    out = []
    if mt == 'movie':
        out.append(Candidate(ADD_MOVIE, _make(LIBRARY, MOVIE, {'movieid': snap.dbid},
                                              snap.title or snap.label, snap)))
        return out
    if mt == 'tvshow':
        out.append(Candidate(ADD_SHOW, _make(LIBRARY, SHOW, {'tvshowid': snap.dbid}, show, snap,
                                             show_title=show)))
        return out
    if snap.tvshowid <= 0:
        return out  # the lookup failed; we can't say which show this belongs to
    show_entry = _make(LIBRARY, SHOW, {'tvshowid': snap.tvshowid}, show, snap, show_title=show,
                       art=show_art(snap.art), plot='')
    if mt == 'season':
        label = season_label(snap)
        out.append(Candidate(ADD_SEASON, _make(
            LIBRARY, SEASON, {'tvshowid': snap.tvshowid, 'season': snap.season},
            season_title(show, label), snap, show_title=show, season_label=label,
            art=season_art(snap.art))))
        out.append(Candidate(ADD_SHOW, show_entry))
        return out
    # episode
    out.append(Candidate(ADD_SHOW, show_entry))
    if snap.season >= 0:
        label = 'Specials' if snap.season == 0 else f'Season {snap.season}'
        out.append(Candidate(ADD_SEASON, _make(
            LIBRARY, SEASON, {'tvshowid': snap.tvshowid, 'season': snap.season},
            season_title(show, label), snap, show_title=show, season_label=label,
            art=season_art(snap.art), plot='')))
    out.append(Candidate(ADD_ITEM, _make(LIBRARY, ITEM, {'episodeid': snap.dbid},
                                         _item_title(snap), snap, show_title=show)))
    return out


def usable_parent(snap):
    """The folder the item was listed in, unless that's the item itself or an add-on's main menu."""
    parent = snap.parent_path
    if not parent or parent.rstrip('/') == snap.path.rstrip('/'):
        return ''
    if parent.startswith('plugin://'):
        _, _, tail = parent[len('plugin://'):].partition('/')
        if not tail.strip('/'):
            return ''
    return parent


def _addon(snap):
    origin = snap.addon_name
    out = []
    parent = usable_parent(snap)
    parent_usable = bool(parent)

    if snap.is_folder:
        if snap.media_type == 'season' or is_season_label(snap.label):
            label = season_label(snap)
            show = resolve_show_name(snap, label)
            out.append(Candidate(ADD_SEASON, _make(
                ADDON, SEASON, {'path': snap.path}, season_title(show, label), snap,
                show_title=show, season_label=label, origin=origin, art=season_art(snap.art)),
                needs_show_name=not show))
            if parent_usable:
                # the folder the user is in holds the seasons, so it's the show
                out.append(Candidate(ADD_SHOW, _make(
                    ADDON, SHOW, {'path': parent}, show, snap, show_title=show, origin=origin,
                    art=show_art(snap.art), plot=''), needs_show_name=not show))
            return out
        title = snap.tvshowtitle or snap.title or snap.label
        verb = ADD_SHOW if snap.media_type == 'tvshow' else ADD_FOLDER
        out.append(Candidate(verb, _make(ADDON, SHOW, {'path': snap.path}, title, snap,
                                         show_title=title, origin=origin)))
        return out

    # a playable item: offer the folder it's in (the show or season), then the item itself
    if parent_usable and snap.media_type != 'movie':
        category = snap.plugin_category.strip()
        show = resolve_show_name(snap)
        if is_season_label(category):
            out.append(Candidate(ADD_SEASON, _make(
                ADDON, SEASON, {'path': parent}, season_title(show, category), snap,
                show_title=show, season_label=category, origin=origin,
                art=season_art(snap.art), plot=''), needs_show_name=not show))
        elif show:
            out.append(Candidate(ADD_SHOW, _make(
                ADDON, SHOW, {'path': parent}, show, snap, show_title=show, origin=origin,
                art=show_art(snap.art), plot='')))
        else:
            out.append(Candidate(ADD_FOLDER, _make(
                ADDON, SHOW, {'path': parent}, '', snap, origin=origin,
                art=show_art(snap.art), plot=''), needs_show_name=True))
    kind = MOVIE if snap.media_type == 'movie' else ITEM
    out.append(Candidate(ADD_MOVIE if kind == MOVIE else ADD_ITEM, _make(
        ADDON, kind, {'path': snap.path}, _item_title(snap), snap,
        show_title=snap.tvshowtitle, origin=origin)))
    return out


def with_show_name(candidate, show):
    """Fill in a show name found (or typed) after candidates() ran."""
    e = candidate.entry
    e.show_title = show
    e.display_title = season_title(show, e.season_label) if e.kind == SEASON else show
    candidate.needs_show_name = False
    return candidate

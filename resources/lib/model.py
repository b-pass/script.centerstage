# -*- coding: utf-8 -*-
"""Data model shared by every part of the add-on. Kodi-free."""
from dataclasses import dataclass, field, asdict
import re
import time

# where an entry's episodes come from
LIBRARY = 'library'
PVR = 'pvr'
ADDON = 'addon'  # any other plugin:// (or plain VFS) folder or item, listed through Files.GetDirectory
MOVIES = 'movies'  # the "Movies" title: the stored movies, gathered into one row (never stored)
MOVIES_ID = 'movies'
NEWEST = 'newest'  # the "<group> - Newest" title: the shown recordings, newest first (never stored)
NEWEST_ID = 'newest'

# what an entry is
SHOW = 'show'      # a whole series
SEASON = 'season'  # one season of a series
MOVIE = 'movie'
ITEM = 'item'      # any single playable thing (an episode, a clip, an add-on movie)

SINGLE_KINDS = (MOVIE, ITEM)

_ARTICLES = re.compile(r'^(the|a|an)\s+', re.IGNORECASE)
# Kodi's label formatting tags only, so a title like "[REC]" or an add-on's "[Flex]" badge stays
_TAGS = re.compile(r'\[/?(?:B|I|LIGHT|UPPERCASE|LOWERCASE|CAPITALIZE|TABS|CR|COLOR(?: [^\]]*)?)\]',
                   re.IGNORECASE)
_BADGES = re.compile(r'^(?:\[[^\]]*\]\s*)+')  # "[Flex] ", "[Bonus Borrow] " before a title


@dataclass
class Entry:
    """One row of the left-hand list."""
    id: str
    source: str
    kind: str
    ref: dict                 # source-specific, see entry_id()
    display_title: str
    show_title: str = ''
    season_label: str = ''
    art: dict = field(default_factory=dict)
    plot: str = ''
    year: int = 0
    added: float = 0.0
    origin: str = ''          # human name of where it came from ("Library", an add-on's name, ...)
    group: str = ''           # the recording group it's shown in; "" for all of them
    auto: bool = False        # computed on the fly (PVR series), never stored
    count: int = 0            # number of recordings, for PVR series; never stored
    members: list = field(default_factory=list)  # the "Movies" title's movies; never stored

    RUNTIME_FIELDS = ('auto', 'count', 'members')

    @property
    def is_single(self):
        return self.kind in SINGLE_KINDS

    def to_dict(self):
        d = asdict(self)
        for k in self.RUNTIME_FIELDS:
            d.pop(k)
        return d

    @classmethod
    def from_dict(cls, d):
        known = {k: d[k] for k in cls.__dataclass_fields__
                 if k in d and k not in cls.RUNTIME_FIELDS}
        return cls(**known)


@dataclass
class Episode:
    """One row of the top-right list: something to play, or a folder (e.g. a season) to open."""
    label: str
    play: dict                # the "item" object for JSON-RPC Player.Open; empty for folders
    label2: str = ''          # right-hand text when the window has nothing better (folders)
    title: str = ''
    season: int = -1
    episode: int = -1
    plot: str = ''
    art: dict = field(default_factory=dict)
    playcount: int = 0
    resume: float = 0.0       # seconds
    total: float = 0.0        # seconds, for the resume point
    runtime: int = 0          # seconds
    date: str = ''            # aired/recorded: "YYYY-MM-DD", or "YYYY-MM-DD HH:MM" local time
    channel: str = ''         # recordings only
    untitled: bool = False    # no name of its own (none, or "Untitled"): the window shows
                              # "Season X, Episode Y" instead of label when it has the numbers
    sort: tuple = ()          # ordering key within the entry
    media_type: str = 'episode'
    is_folder: bool = False
    browse: dict = field(default_factory=dict)  # for folders: what to pass back to list it
    parent: bool = False      # the ".." row
    entry_id: str = ''        # in the "Movies" title: the stored movie entry this row is
    show: str = ''            # in the "Newest" title: the series, shown before the label

    def to_dict(self):
        d = asdict(self)
        d['sort'] = list(self.sort)
        return d

    @classmethod
    def from_dict(cls, d):
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        known['sort'] = tuple(known.get('sort') or ())
        return cls(**known)


def entry_id(source, kind, ref):
    """Stable id for an entry, so adding the same thing twice finds the existing one."""
    if source == LIBRARY:
        if kind == SHOW:
            return f'library:tvshow:{ref["tvshowid"]}'
        if kind == SEASON:
            return f'library:season:{ref["tvshowid"]}:{ref["season"]}'
        if kind == MOVIE:
            return f'library:movie:{ref["movieid"]}'
        return f'library:episode:{ref["episodeid"]}'
    if source == PVR:
        return f'pvr:{pvr_key(ref["title"])}'
    return f'addon:{kind}:{ref["path"]}'


def parent_row(label='..'):
    return Episode(label=label, play={}, is_folder=True, parent=True, media_type='')


def plain(text):
    """text without Kodi's label formatting tags ([B], [COLOR yellow], ...)."""
    return _TAGS.sub('', text or '')


def pvr_key(title):
    return ' '.join(title.split()).casefold()


def sort_title(title):
    """Alphabetical sort key that ignores formatting tags, leading bracketed badges such as an
    add-on's "[Flex] ", and a leading "The", "A" or "An"."""
    text = plain(title).strip()
    text = _BADGES.sub('', text) or text
    return _ARTICLES.sub('', text).casefold()


def is_untitled(title):
    return (title or '').strip().casefold() in ('', 'untitled')


def episode_code(season, episode):
    if season is not None and season >= 0 and episode is not None and episode > 0:
        return f'S{season:02d}E{episode:02d}'
    return ''


def details_code(season, episode):
    """The details pane's form of episode_code(): "S2 E09"."""
    if episode_code(season, episode):
        return f'S{season} E{episode:02d}'
    return ''


def parse_date(text):
    """An Episode.date as (struct_time, has_time), or None when it isn't one."""
    text = (text or '').strip()
    for fmt, has_time in (('%Y-%m-%d %H:%M:%S', True), ('%Y-%m-%d %H:%M', True),
                          ('%Y-%m-%d', False)):
        try:
            return time.strptime(text, fmt), has_time
        except ValueError:
            pass
    return None


def format_time(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'

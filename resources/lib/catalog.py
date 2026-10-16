# -*- coding: utf-8 -*-
"""Builds the left-hand list and each entry's episode list from the store and the sources.
Kodi-free."""
from jsonrpc import RpcError
from model import Entry, Episode, LIBRARY, MOVIE, MOVIES, MOVIES_ID, NEWEST, PVR, SHOW, sort_title
from sources import library, pvr, addon

SORT_TITLE = 0
SORT_ADDED = 1


def movies_entry(movies, title):
    """The "Movies" title: every movie entry in one row, with the newest one's art."""
    newest = max(movies, key=lambda e: e.added)
    return Entry(id=MOVIES_ID, source=MOVIES, kind=SHOW, ref={}, display_title=title,
                 art=dict(newest.art), added=newest.added, auto=True,
                 members=sorted(movies, key=lambda e: (sort_title(e.display_title), e.id)))


def rows(stored, pvr_entries, sort_mode=SORT_TITLE, group=None, movies_title=None,
         newest_title=None):
    """Every entry, all sources mixed together. With a recording group, only the stored entries
    for that group or for all groups (pvr_entries should already be limited to it). With a
    movies_title, the stored movies are gathered into one title of that name. With a
    newest_title and any DVR series, a title of that name listing their recordings newest first
    comes before everything, whatever the sort order."""
    if group is not None:
        stored = [e for e in stored if not e.group or e.group == group]
    if movies_title:
        movies = [e for e in stored if e.kind == MOVIE]
        if movies:
            stored = [e for e in stored if e.kind != MOVIE] + [movies_entry(movies, movies_title)]
    everything = list(stored) + list(pvr_entries)
    if sort_mode == SORT_ADDED:
        out = sorted(everything, key=lambda e: (-e.added, sort_title(e.display_title), e.id))
    else:
        out = sorted(everything, key=lambda e: (sort_title(e.display_title), e.id))
    if newest_title and pvr_entries:
        out.insert(0, pvr.newest_entry(pvr_entries, newest_title))
    return out


def load_rows(rpc, entry, kodi_major, recordings=None, browse=None, season_word='{}/{}'):
    """One level of an entry: its top level when browse is None, else the folder browse names."""
    if entry.source == LIBRARY:
        return library.rows(rpc, entry, browse, season_word)
    if entry.source == PVR:
        return pvr.episodes(rpc, entry, recordings)
    if entry.source == NEWEST:
        return pvr.newest(rpc, entry, recordings)
    if entry.source == MOVIES:
        return movie_rows(rpc, entry, kodi_major)
    return addon.rows(rpc, entry, kodi_major, browse)


def movie_rows(rpc, entry, kodi_major):
    """The "Movies" title's rows: one per movie, by its name in Center Stage. Each row's entry_id
    is the movie's entry. A movie that can't be read (e.g. gone from the library) still gets a
    row, so it can be removed."""
    out = []
    for movie in entry.members:
        try:
            found = load_rows(rpc, movie, kodi_major)
        except (RpcError, KeyError):
            found = []
        row = found[0] if found else Episode(label=movie.display_title, play={},
                                             title=movie.display_title, plot=movie.plot,
                                             art=dict(movie.art), media_type='movie')
        row.label = movie.display_title
        row.sort = (sort_title(movie.display_title), movie.id)
        row.entry_id = movie.id
        out.append(row)
    return out


def arrange(rows, newest_first=False, hide_watched=False, limit=None):
    """Folders keep their places; playable rows can be reversed or have watched ones hidden.
    limit keeps that many rows from the top, after hiding."""
    out = sorted(rows, key=lambda e: e.sort)
    if newest_first:
        slots = [n for n, e in enumerate(out) if not e.is_folder]
        playable = [out[n] for n in slots]
        for n, e in zip(slots, reversed(playable)):
            out[n] = e
    if hide_watched:
        out = [e for e in out if e.is_folder or e.playcount <= 0]
    return out if limit is None else out[:limit]

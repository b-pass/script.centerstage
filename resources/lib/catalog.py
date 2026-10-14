# -*- coding: utf-8 -*-
"""Builds the left-hand list and each entry's episode list from the store and the sources.
Kodi-free."""
from model import LIBRARY, PVR, sort_title
from sources import library, pvr, addon

SORT_TITLE = 0
SORT_ADDED = 1


def rows(stored, pvr_entries, sort_mode=SORT_TITLE, group=None):
    """Every entry, all sources mixed together. With a recording group, only the stored entries
    for that group or for all groups (pvr_entries should already be limited to it)."""
    if group is not None:
        stored = [e for e in stored if not e.group or e.group == group]
    everything = list(stored) + list(pvr_entries)
    if sort_mode == SORT_ADDED:
        return sorted(everything, key=lambda e: (-e.added, sort_title(e.display_title), e.id))
    return sorted(everything, key=lambda e: (sort_title(e.display_title), e.id))


def load_rows(rpc, entry, kodi_major, recordings=None, browse=None, season_word='{}/{}'):
    """One level of an entry: its top level when browse is None, else the folder browse names."""
    if entry.source == LIBRARY:
        return library.rows(rpc, entry, browse, season_word)
    if entry.source == PVR:
        return pvr.episodes(rpc, entry, recordings)
    return addon.rows(rpc, entry, kodi_major, browse)


def arrange(rows, newest_first=False, hide_watched=False):
    """Folders keep their places; playable rows can be reversed or have watched ones hidden."""
    out = sorted(rows, key=lambda e: e.sort)
    if newest_first:
        slots = [n for n, e in enumerate(out) if not e.is_folder]
        playable = [out[n] for n in slots]
        for n, e in zip(slots, reversed(playable)):
            out[n] = e
    if hide_watched:
        out = [e for e in out if e.is_folder or e.playcount <= 0]
    return out

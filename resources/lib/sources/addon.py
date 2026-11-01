# -*- coding: utf-8 -*-
"""Folders and items from other add-ons (any plugin:// or VFS path), listed through JSON-RPC
Files.GetDirectory, which runs the other add-on with no UI.

A folder entry is browsed one level at a time: its listing is shown as it is, subfolders
(seasons, "Extras", "Next page", ...) open in place. Nothing is guessed about the structure.

On Kodi 22+, media "files" plus non-basic properties makes Kodi look up watched/resume state from
the video database (FileOperations.cpp NeedsLibraryLookup). Kodi 21 has no such lookup, so there
we ask for media "video" and only get what the add-on itself set.
"""
import re

from model import Episode, SINGLE_KINDS, MOVIE, plain, runs
from sources.common import episode_from_item, folder_from_item

ITEM_PROPS = ['title', 'plot', 'art', 'season', 'episode', 'showtitle', 'playcount', 'resume',
              'runtime', 'firstaired', 'premiered', 'customproperties']
MAX_SKIP = 3  # how many single-folder levels to walk through automatically
_BACK = re.compile(r'[\s<«‹←-]*(?:\.\.+[\s-]*)?(?:(?:go\s+)?back)?[\s.]*', re.IGNORECASE)


def list_dir(rpc, path, kodi_major):
    media = 'files' if kodi_major >= 22 else 'video'
    result = rpc.call('Files.GetDirectory', directory=path, media=media, properties=ITEM_PROPS)
    return [i for i in result.get('files') or [] if i.get('file')]


def _is_folder(item):
    return item.get('filetype') == 'directory'


def is_back(item):
    """An add-on's own "..", "Back" or ".. Back" folder, which leads out of the listing."""
    if not _is_folder(item) or item.get('type') not in (None, '', 'unknown'):
        return False
    label = plain(item.get('label')).strip()
    return ('..' in label or 'back' in label.casefold()) and bool(_BACK.fullmatch(label))


def _play(path, run):
    return {'file': path, 'run': True} if run else {'file': path}


def _row(item, n):
    if _is_folder(item):
        media_type = 'season' if item.get('type') == 'season' else ''
        return folder_from_item(item, {'path': item['file']}, (n,), media_type=media_type)
    media_type = 'movie' if item.get('type') == 'movie' else 'episode'
    playable = (item.get('customproperties') or {}).get('isplayable')  # Kodi lowercases the key
    return episode_from_item(item, _play(item['file'], runs(item['file'], playable)), (n,),
                             media_type=media_type, name=_name(item))


def _name(item):
    """The row's name: the add-on's label from the title on, as Kodi would show it, keeping what
    the add-on adds after it ("(not borrowed)") but not a number before it ("1x03. "), which the
    details show. The title alone when the label doesn't hold it."""
    title = plain(item.get('title')).strip()
    label = plain(item.get('label'))
    at = label.find(title) if title else -1
    return label[at:].strip() if at >= 0 else ''


def rows(rpc, entry, kodi_major, browse=None):
    """One level of an add-on entry: its own folder when browse is None, else browse['path']."""
    if entry.kind in SINGLE_KINDS:
        return [Episode(label=entry.display_title,
                        play=_play(entry.ref['path'], entry.ref.get('run')),
                        title=entry.display_title, plot=entry.plot, art=dict(entry.art),
                        media_type='movie' if entry.kind == MOVIE else 'episode')]
    path = (browse or {}).get('path') or entry.ref['path']
    items = list_dir(rpc, path, kodi_major)
    if browse is None:
        # the entry's own level: the left list is its parent, so drop the add-on's way back out
        items = [i for i in items if not is_back(i)]
        # a show whose folder holds just one folder (one season): go straight into it
        for _ in range(MAX_SKIP):
            if len(items) != 1 or not _is_folder(items[0]):
                break
            items = [i for i in list_dir(rpc, items[0]['file'], kodi_major) if not is_back(i)]
    return [_row(i, n) for n, i in enumerate(items)]


def peek_show_title(rpc, path, kodi_major):
    """The show title that items inside path carry, looking one folder deeper if needed."""
    items = list_dir(rpc, path, kodi_major)
    for i in items:
        if i.get('showtitle'):
            return i['showtitle']
    folder = next((i for i in items if _is_folder(i)), None)
    if folder:
        for i in list_dir(rpc, folder['file'], kodi_major):
            if i.get('showtitle'):
                return i['showtitle']
    return ''

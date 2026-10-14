# -*- coding: utf-8 -*-
"""Episode lists of add-on entries, kept on disk so reopening the window doesn't re-run every
add-on. Kodi-free."""
import hashlib
import json
import os
import time

from model import Episode


class EpisodeCache:
    def __init__(self, folder, clock=time.time):
        self.folder = folder
        self.clock = clock

    def _path(self, entry_id):
        name = hashlib.sha1(entry_id.encode('utf-8')).hexdigest()
        return os.path.join(self.folder, f'{name}.json')

    def get(self, entry_id):
        """(episodes, age in seconds), or (None, None) if nothing is cached."""
        try:
            with open(self._path(entry_id), encoding='utf-8') as f:
                data = json.load(f)
            episodes = [Episode.from_dict(d) for d in data['episodes']]
            return episodes, max(0.0, self.clock() - float(data['saved']))
        except (OSError, ValueError, KeyError, TypeError):
            return None, None

    def put(self, entry_id, episodes):
        os.makedirs(self.folder, exist_ok=True)
        path = self._path(entry_id)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'id': entry_id, 'saved': self.clock(),
                       'episodes': [e.to_dict() for e in episodes]}, f, ensure_ascii=False)
        os.replace(tmp, path)

    def drop(self, entry_id):
        try:
            os.remove(self._path(entry_id))
        except OSError:
            pass

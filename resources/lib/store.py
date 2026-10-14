# -*- coding: utf-8 -*-
"""The user's saved entries, as one JSON file in the add-on's profile folder. Kodi-free.

The context-menu script and the window run in separate interpreters and can both write, so every
change re-reads the file first and saves it atomically.
"""
import json
import os
import time

from model import Entry

FILENAME = 'entries.json'
VERSION = 1


class Store:
    def __init__(self, folder, clock=time.time):
        self.folder = folder
        self.path = os.path.join(folder, FILENAME)
        self.clock = clock

    def _load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data.setdefault('version', VERSION)
        data.setdefault('entries', [])
        data.setdefault('hidden_pvr', {})  # pvr_key -> title as it was shown
        data.setdefault('renames', {})
        data.setdefault('last_group', None)  # recording group last picked; None for all
        return data

    def _save(self, data):
        os.makedirs(self.folder, exist_ok=True)
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    # reading

    def entries(self):
        data = self._load()
        result = []
        for d in data['entries']:
            try:
                result.append(Entry.from_dict(d))
            except TypeError:
                continue  # a malformed row; skip it rather than lose the whole list
        return result

    def get(self, entry_id):
        return next((e for e in self.entries() if e.id == entry_id), None)

    def hidden_pvr(self):
        """{pvr_key: title} of the DVR series the user hid."""
        return dict(self._load()['hidden_pvr'])

    def renames(self):
        return dict(self._load()['renames'])

    def last_group(self):
        return self._load()['last_group']

    # writing

    def add(self, entry):
        """Save entry. Returns False (and changes nothing) if an entry with its id already exists."""
        data = self._load()
        if any(d.get('id') == entry.id for d in data['entries']):
            return False
        if not entry.added:
            entry.added = self.clock()
        data['entries'].append(entry.to_dict())
        self._save(data)
        return True

    def remove(self, entry_id):
        data = self._load()
        before = len(data['entries'])
        data['entries'] = [d for d in data['entries'] if d.get('id') != entry_id]
        data['renames'].pop(entry_id, None)
        self._save(data)
        return len(data['entries']) != before

    def rename(self, entry_id, title):
        """Stored entries get a new display_title; computed ones (DVR series) get an override."""
        data = self._load()
        for d in data['entries']:
            if d.get('id') == entry_id:
                d['display_title'] = title
                break
        else:
            data['renames'][entry_id] = title
        self._save(data)

    def set_group(self, entry_id, group):
        """Show a stored entry in one recording group only, or in all of them (group "")."""
        data = self._load()
        for d in data['entries']:
            if d.get('id') == entry_id:
                d['group'] = group
                self._save(data)
                return True
        return False

    def set_last_group(self, group):
        data = self._load()
        if data['last_group'] != group:
            data['last_group'] = group
            self._save(data)

    def hide_pvr(self, key, title):
        data = self._load()
        data['hidden_pvr'][key] = title
        self._save(data)

    def unhide_pvr(self, key):
        data = self._load()
        if data['hidden_pvr'].pop(key, None) is not None:
            self._save(data)

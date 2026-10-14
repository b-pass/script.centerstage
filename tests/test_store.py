import json
import os
import tempfile
import unittest

import tests  # noqa: F401  (sets sys.path)
from cache import EpisodeCache
from jsonrpc import Rpc, RpcError
from model import Entry, Episode, ADDON, SHOW, PVR, entry_id
from store import Store


def show(path='p://a', title='A'):
    ref = {'path': path}
    return Entry(id=entry_id(ADDON, SHOW, ref), source=ADDON, kind=SHOW, ref=ref,
                 display_title=title)


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.dir.name, 'profile'), clock=lambda: 1000.0)

    def tearDown(self):
        self.dir.cleanup()

    def test_empty(self):
        self.assertEqual(self.store.entries(), [])
        self.assertEqual(self.store.hidden_pvr(), {})

    def test_add_once(self):
        self.assertTrue(self.store.add(show()))
        self.assertFalse(self.store.add(show(title='Other name')))
        (e,) = self.store.entries()
        self.assertEqual((e.display_title, e.added), ('A', 1000.0))

    def test_round_trip_does_not_store_runtime_fields(self):
        e = show()
        e.auto, e.count = True, 3
        self.store.add(e)
        with open(self.store.path) as f:
            raw = json.load(f)['entries'][0]
        self.assertNotIn('auto', raw)
        self.assertNotIn('count', raw)
        self.assertEqual(self.store.get(e.id).ref, {'path': 'p://a'})

    def test_remove_and_rename(self):
        a, b = show('p://a', 'A'), show('p://b', 'B')
        self.store.add(a)
        self.store.add(b)
        self.store.rename(b.id, 'Bee')
        self.assertTrue(self.store.remove(a.id))
        self.assertEqual([e.display_title for e in self.store.entries()], ['Bee'])

    def test_rename_of_computed_entry_is_an_override(self):
        pid = entry_id(PVR, SHOW, {'title': 'News'})
        self.store.rename(pid, 'The News')
        self.assertEqual(self.store.renames(), {pid: 'The News'})

    def test_groups(self):
        a = show()
        self.store.add(a)
        self.assertEqual(self.store.get(a.id).group, '')  # all groups
        self.assertTrue(self.store.set_group(a.id, 'Emily'))
        self.assertEqual(self.store.get(a.id).group, 'Emily')
        self.assertFalse(self.store.set_group('addon:show:p://nope', 'Emily'))
        self.assertIsNone(self.store.last_group())
        self.store.set_last_group('Bryan')
        self.assertEqual(self.store.last_group(), 'Bryan')

    def test_hide_and_unhide_pvr(self):
        self.store.hide_pvr('news', 'News')
        self.assertEqual(self.store.hidden_pvr(), {'news': 'News'})
        self.store.unhide_pvr('news')
        self.assertEqual(self.store.hidden_pvr(), {})

    def test_corrupt_file_reads_as_empty(self):
        os.makedirs(self.store.folder)
        with open(self.store.path, 'w') as f:
            f.write('{not json')
        self.assertEqual(self.store.entries(), [])
        self.store.add(show())
        self.assertEqual(len(self.store.entries()), 1)


class CacheTest(unittest.TestCase):
    def test_put_get_age_drop(self):
        with tempfile.TemporaryDirectory() as d:
            now = [100.0]
            cache = EpisodeCache(d, clock=lambda: now[0])
            self.assertEqual(cache.get('x'), (None, None))
            cache.put('x', [Episode('Pilot', {'file': 'p://1'}, sort=(0,))])
            now[0] = 130.0
            eps, age = cache.get('x')
            self.assertEqual((eps[0].label, eps[0].sort, age), ('Pilot', (0,), 30.0))
            cache.drop('x')
            self.assertEqual(cache.get('x'), (None, None))


class RpcTest(unittest.TestCase):
    def test_result_and_error(self):
        rpc = Rpc(lambda raw: json.dumps({'id': 1, 'result': {'ok': json.loads(raw)['method']}}))
        self.assertEqual(rpc.call('JSONRPC.Ping'), {'ok': 'JSONRPC.Ping'})
        bad = Rpc(lambda raw: json.dumps({'id': 1, 'error': {'message': 'Invalid params.'}}))
        with self.assertRaises(RpcError):
            bad.call('X')
        with self.assertRaises(RpcError):
            Rpc(lambda raw: 'garbage').call('X')


if __name__ == '__main__':
    unittest.main()

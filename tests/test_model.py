import unittest

import tests  # noqa: F401  (sets sys.path)
from model import Episode, is_untitled, parse_date, plain


class ParseDate(unittest.TestCase):
    def test_forms(self):
        when, has_time = parse_date('2026-09-01 14:05')
        self.assertEqual((when.tm_year, when.tm_mon, when.tm_mday, when.tm_hour, when.tm_min),
                         (2026, 9, 1, 14, 5))
        self.assertTrue(has_time)
        self.assertTrue(parse_date('2026-09-01 14:05:30')[1])
        self.assertFalse(parse_date('2005-03-24')[1])

    def test_not_a_date(self):
        for text in ('', None, '2026', 'yesterday'):
            self.assertIsNone(parse_date(text))


class EpisodeCompat(unittest.TestCase):
    def test_cached_rows_without_channel_still_load(self):
        ep = Episode.from_dict({'label': 'x', 'play': {}, 'date': '2026-09-01'})
        self.assertEqual(ep.channel, '')


class Untitled(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(plain('[COLOR yellow]Alone[/COLOR]'), 'Alone')
        self.assertEqual(plain('[B]S01E02[/B] · [I]x[/I]'), 'S01E02 · x')
        self.assertEqual(plain('Episode [2]'), 'Episode [2]')
        self.assertEqual(plain(None), '')
        self.assertEqual(plain('[Flex] [REC] [CR]x[/B]'), '[Flex] [REC] x')

    def test_sort_title(self):
        from model import sort_title
        self.assertEqual(sort_title('The Office'), 'office')
        self.assertEqual(sort_title('[Bonus Borrow] [Flex] An Idiot Abroad'), 'idiot abroad')
        self.assertEqual(sort_title('[COLOR yellow]Alone[/COLOR]'), 'alone')
        self.assertEqual(sort_title('[REC]'), '[rec]')

    def test_untitled(self):
        for title in ('', None, '  ', 'Untitled', ' untitled '):
            self.assertTrue(is_untitled(title), title)
        for title in ('Pilot', 'Untitled Goose Episode'):
            self.assertFalse(is_untitled(title), title)

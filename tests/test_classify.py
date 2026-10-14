import unittest

import tests  # noqa: F401  (sets sys.path)
import classify
from classify import Snapshot, candidates, with_show_name
from model import ADDON, LIBRARY, SEASON, SHOW, ITEM, MOVIE

OFFICE = 'plugin://plugin.video.demo/?action=show&id=office'
SEASON1 = 'plugin://plugin.video.demo/?action=season&id=office&n=1'
EP = 'plugin://plugin.video.demo/?action=play&id=office-1-1'


class SeasonLabels(unittest.TestCase):
    def test_season_like(self):
        for text in ('Season 1', 'season 12', 'Series 3', 'S2', 'S 02', 'Staffel 4',
                     'Specials', 'Season 1 (2005)', 'Temporada 2'):
            self.assertTrue(classify.is_season_label(text), text)

    def test_not_season_like(self):
        for text in ('The Office', 'Seasons of Love', 'Sherlock', '', 'Survivor 2000'):
            self.assertFalse(classify.is_season_label(text), text)


class AddonSeasonNaming(unittest.TestCase):
    def season(self, **kw):
        base = dict(label='Season 1', path=SEASON1, is_folder=True, parent_path=OFFICE,
                    addon_name='Demo')
        base.update(kw)
        return Snapshot(**base)

    def test_show_title_from_item(self):
        c = candidates(self.season(tvshowtitle='The Office', plugin_category='Whatever'))[0]
        self.assertEqual(c.verb, classify.ADD_SEASON)
        self.assertEqual(c.entry.display_title, 'The Office - Season 1')
        self.assertEqual(c.entry.show_title, 'The Office')
        self.assertEqual(c.entry.season_label, 'Season 1')
        self.assertEqual(c.entry.source, ADDON)
        self.assertEqual(c.entry.ref, {'path': SEASON1})
        self.assertFalse(c.needs_show_name)

    def test_show_title_from_plugin_category(self):
        c = candidates(self.season(plugin_category='The Office'))[0]
        self.assertEqual(c.entry.display_title, 'The Office - Season 1')

    def test_category_that_is_the_addon_name_is_ignored(self):
        c = candidates(self.season(plugin_category='Demo'))[0]
        self.assertTrue(c.needs_show_name)
        self.assertEqual(c.entry.display_title, 'Season 1')

    def test_category_that_is_a_season_is_ignored(self):
        c = candidates(self.season(plugin_category='Season 1'))[0]
        self.assertTrue(c.needs_show_name)

    def test_name_filled_in_later(self):
        c = candidates(self.season())[0]
        self.assertTrue(c.needs_show_name)
        with_show_name(c, 'The Office')
        self.assertEqual(c.entry.display_title, 'The Office - Season 1')
        self.assertFalse(c.needs_show_name)

    def test_parent_offered_as_the_show(self):
        cands = candidates(self.season(tvshowtitle='The Office'))
        self.assertEqual([c.verb for c in cands], [classify.ADD_SEASON, classify.ADD_SHOW])
        show = cands[1].entry
        self.assertEqual((show.kind, show.ref, show.display_title),
                         (SHOW, {'path': OFFICE}, 'The Office'))

    def test_addon_root_is_not_offered(self):
        cands = candidates(self.season(tvshowtitle='The Office',
                                       parent_path='plugin://plugin.video.demo/'))
        self.assertEqual([c.verb for c in cands], [classify.ADD_SEASON])

    def test_season_number_without_a_season_label(self):
        c = candidates(self.season(label='Year one', media_type='season', season=1,
                                   tvshowtitle='The Office'))[0]
        self.assertEqual(c.entry.display_title, 'The Office - Season 1')


class AddonOther(unittest.TestCase):
    def test_show_folder(self):
        snap = Snapshot(label='The Office', path=OFFICE, is_folder=True, media_type='tvshow',
                        parent_path='plugin://plugin.video.demo/?action=shows', addon_name='Demo')
        (c,) = candidates(snap)
        self.assertEqual((c.verb, c.entry.kind, c.entry.display_title, c.entry.origin),
                         (classify.ADD_SHOW, SHOW, 'The Office', 'Demo'))

    def test_generic_folder(self):
        snap = Snapshot(label='Cooking', path='plugin://x/?c=1', is_folder=True)
        (c,) = candidates(snap)
        self.assertEqual(c.verb, classify.ADD_FOLDER)

    def test_episode_inside_a_season(self):
        snap = Snapshot(label='Pilot', path=EP, title='Pilot', tvshowtitle='The Office',
                        season=1, episode=1, media_type='episode', parent_path=SEASON1,
                        plugin_category='Season 1', addon_name='Demo')
        folder, item = candidates(snap)
        self.assertEqual((folder.verb, folder.entry.display_title, folder.entry.ref),
                         (classify.ADD_SEASON, 'The Office - Season 1', {'path': SEASON1}))
        self.assertEqual((item.verb, item.entry.kind, item.entry.display_title),
                         (classify.ADD_ITEM, ITEM, 'The Office - S01E01 Pilot'))

    def test_episode_in_an_unnamed_folder(self):
        snap = Snapshot(label='Pilot', path=EP, parent_path=SEASON1)
        folder, _ = candidates(snap)
        self.assertEqual(folder.verb, classify.ADD_FOLDER)
        self.assertTrue(folder.needs_show_name)
        with_show_name(folder, 'Mystery Show')
        self.assertEqual(folder.entry.display_title, 'Mystery Show')

    def test_movie(self):
        snap = Snapshot(label='Film', title='Film', path='plugin://x/?play=1',
                        media_type='movie', parent_path='plugin://x/?movies=1')
        (c,) = candidates(snap)
        self.assertEqual((c.verb, c.entry.kind), (classify.ADD_MOVIE, MOVIE))


class Library(unittest.TestCase):
    def test_movie(self):
        snap = Snapshot(label='Film', title='Film', path='/media/film.mkv', media_type='movie',
                        dbid=7)
        (c,) = candidates(snap)
        self.assertEqual((c.entry.source, c.entry.ref, c.entry.id),
                         (LIBRARY, {'movieid': 7}, 'library:movie:7'))

    def test_season(self):
        snap = Snapshot(label='Season 2', path='videodb://tvshows/titles/4/2/', is_folder=True,
                        media_type='season', dbid=31, season=2, tvshowtitle='The Office',
                        tvshowid=4)
        season, show = candidates(snap)
        self.assertEqual((season.entry.kind, season.entry.ref, season.entry.display_title),
                         (SEASON, {'tvshowid': 4, 'season': 2}, 'The Office - Season 2'))
        self.assertEqual((show.entry.ref, show.entry.display_title),
                         ({'tvshowid': 4}, 'The Office'))

    def test_episode(self):
        snap = Snapshot(label='Pilot', title='Pilot', path='/tv/office/s01e01.mkv',
                        media_type='episode', dbid=90, season=1, episode=1,
                        tvshowtitle='The Office', tvshowid=4)
        verbs = [c.verb for c in candidates(snap)]
        self.assertEqual(verbs, [classify.ADD_SHOW, classify.ADD_SEASON, classify.ADD_ITEM])

    def test_episode_without_show_lookup_offers_nothing(self):
        snap = Snapshot(label='Pilot', path='/tv/x.mkv', media_type='episode', dbid=90)
        self.assertEqual(candidates(snap), [])

    def test_plugin_item_with_dbid_is_not_library(self):
        snap = Snapshot(label='Film', path='plugin://x/?play=1', media_type='movie', dbid=7)
        self.assertEqual(candidates(snap)[0].entry.source, ADDON)


class Art(unittest.TestCase):
    def test_show_art_prefers_show_images(self):
        art = {'thumb': 'ep.jpg', 'tvshow.poster': 'show.jpg', 'fanart': 'f.jpg'}
        self.assertEqual(classify.show_art(art)['poster'], 'show.jpg')
        self.assertEqual(classify.show_art(art)['fanart'], 'f.jpg')


class Pvr(unittest.TestCase):
    def test_recordings_are_handled_separately(self):
        snap = Snapshot(label='News', path='pvr://recordings/tv/active/News/', is_folder=True)
        self.assertTrue(classify.is_pvr_recording(snap))
        self.assertEqual(candidates(snap), [])
        self.assertEqual(classify.pvr_title(snap), 'News')

    def test_damaged_recording_title_loses_its_colour(self):
        snap = Snapshot(label='[COLOR yellow]Alone[/COLOR]', path='pvr://recordings/tv/active/x')
        self.assertEqual(classify.pvr_title(snap), 'Alone')


if __name__ == '__main__':
    unittest.main()

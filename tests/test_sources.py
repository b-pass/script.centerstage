import os
import time
import unittest

import tests  # noqa: F401  (sets sys.path)
from tests.fakes import FakeRpc
import catalog
from jsonrpc import RpcError
from model import (Entry, ADDON, LIBRARY, PVR, SHOW, SEASON, MOVIE, ITEM, MOVIES, MOVIES_ID,
                   NEWEST, NEWEST_ID, Episode, entry_id)
from sources import addon, library, pvr


def entry(source, kind, ref, title='T', **kw):
    return Entry(id=entry_id(source, kind, ref), source=source, kind=kind, ref=ref,
                 display_title=title, **kw)


RECORDINGS = [
    {'recordingid': 1, 'title': 'News', 'label': 'News', 'showtitle': '',
     'starttime': '2026-09-01 18:00:00', 'channel': 'BBC One', 'art': {'thumb': 'n1.jpg'},
     'resume': {'position': 0, 'total': 0}, 'playcount': 1, 'season': -1, 'episode': -1},
    {'recordingid': 2, 'title': 'The Office', 'showtitle': 'Diversity Day',
     'starttime': '2026-09-03 21:00:00', 'channel': 'NBC', 'art': {},
     'icon': 'nbc.png', 'resume': {'position': 300, 'total': 1320}, 'playcount': 0,
     'season': 1, 'episode': 2, 'plot': 'Michael...'},
    {'recordingid': 3, 'title': 'the  office', 'showtitle': 'Pilot',
     'starttime': '2026-09-02 21:00:00', 'channel': 'NBC', 'art': {'thumb': 'o1.jpg'},
     'season': 1, 'episode': 1},
    {'recordingid': 4, 'title': 'Deleted', 'isdeleted': True, 'starttime': '2026-09-01'},
    {'recordingid': 5, 'title': 'Radio Show', 'radio': True, 'starttime': '2026-09-01'},
]


def series_rows(rpc, title, recs=None):
    """A series' recordings as Python rows (as the Newest title builds them), oldest first. PVR
    series themselves are listed by Kodi."""
    newest = pvr.newest_entry([entry(PVR, SHOW, {'title': title}, title)], 'N')
    return list(reversed(pvr.newest(rpc, newest, recs)))


def set_tz(tz):
    old = os.environ.get('TZ')
    if tz is None:
        os.environ.pop('TZ', None)
    else:
        os.environ['TZ'] = tz
    time.tzset()
    return old


class Pvr(unittest.TestCase):
    def setUp(self):
        self.rpc = FakeRpc({'PVR.GetRecordings': lambda p: {'recordings': RECORDINGS}})
        old = set_tz('UTC')
        self.addCleanup(set_tz, old)

    def test_series_grouped_by_title_ignoring_case_and_spaces(self):
        rows = pvr.series_entries(pvr.recordings(self.rpc))
        titles = sorted((e.display_title, e.count) for e in rows)
        self.assertEqual(titles, [('News', 1), ('The Office', 2)])
        office = next(e for e in rows if e.count == 2)
        self.assertTrue(office.auto)
        self.assertEqual(office.origin, 'NBC')
        self.assertEqual(office.art['thumb'], 'nbc.png')  # newest recording's, via its icon

    def test_series_picture_is_fanart_not_preview(self):
        recs = [dict(r) for r in RECORDINGS]
        recs[0]['art'] = {'thumb': 'preview.jpg', 'fanart': 'series.jpg'}
        recs[2]['art'] = {'thumb': 'o1.jpg', 'fanart': 'office-s1.jpg'}  # older; newest has none
        rows = {e.display_title: e for e in pvr.series_entries(pvr.recordings(FakeRpc(
            {'PVR.GetRecordings': lambda p: {'recordings': recs}})))}
        self.assertEqual(rows['News'].art['thumb'], 'series.jpg')
        self.assertEqual(rows['The Office'].art['thumb'], 'office-s1.jpg')
        eps = series_rows(self.rpc, 'News', recs)
        self.assertEqual(eps[0].art['thumb'], 'preview.jpg')  # episodes keep the preview

    def test_newest_first_whatever_the_sort_with_every_shown_series(self):
        recs = pvr.recordings(self.rpc)
        series = pvr.series_entries(recs, hidden={'news': 'News'})
        stored = [entry(ADDON, SHOW, {'path': 'p://a'}, 'Aardvarks', added=2e9)]
        for mode in (catalog.SORT_TITLE, catalog.SORT_ADDED):
            rows = catalog.rows(stored, series, mode, newest_title='All Stages - Newest')
            self.assertEqual([e.display_title for e in rows],
                             ['All Stages - Newest', 'Aardvarks', 'The Office'])
        newest = rows[0]
        self.assertEqual((newest.id, newest.source, newest.count), (NEWEST_ID, NEWEST, 2))
        self.assertEqual(newest.to_dict().get('count'), None)
        eps = catalog.load_rows(self.rpc, newest, 21, recs)
        self.assertEqual([(e.show, e.label) for e in eps],  # News is hidden
                         [('The Office', 'Diversity Day'), ('The Office', 'Pilot')])
        arranged = catalog.arrange(eps)
        self.assertEqual([e.play['recordingid'] for e in arranged], [2, 3])
        eps[0].playcount = 1
        self.assertEqual([e.play['recordingid'] for e in catalog.arrange(eps, limit=1)], [2])
        self.assertEqual([e.play['recordingid']
                          for e in catalog.arrange(eps, hide_watched=True, limit=1)], [3])
        self.assertEqual(catalog.rows(stored, [], newest_title='X')[0].display_title, 'Aardvarks')

    def test_series_folder_is_the_newest_recordings(self):
        recs = [{'recordingid': 1, 'title': 'Nova', 'starttime': '2026-09-01 18:00:00',
                 'file': 'pvr://recordings/tv/active/Emily/Nova/Nova, TV (PBS), 2026.pvr'},
                {'recordingid': 2, 'title': 'Nova', 'starttime': '2026-09-08 18:00:00',
                 'file': 'pvr://recordings/tv/active/Default/Nova/Nova, TV (PBS), 2026.pvr'}]
        (nova,) = pvr.series_entries(recs)
        self.assertEqual(nova.ref['folder'], 'pvr://recordings/tv/active/Default/Nova?view=flat')
        self.assertEqual(nova.id, 'pvr:nova')  # the folder isn't part of the id
        self.assertEqual(pvr.folder_of({}), '')

    def test_hidden_and_renamed(self):
        recs = pvr.recordings(self.rpc)
        rows = pvr.series_entries(recs, hidden={'news': 'News'},
                                  renames={'pvr:the office': 'Office (US)'})
        self.assertEqual([e.display_title for e in rows], ['Office (US)'])

    def test_episodes_oldest_first_with_episode_names(self):
        eps = series_rows(self.rpc, 'The Office')
        self.assertEqual([e.label for e in eps], ['Pilot', 'Diversity Day'])  # no S01E02 in rows
        self.assertEqual(eps[1].play, {'recordingid': 2})
        self.assertEqual((eps[1].resume, eps[1].total), (300.0, 1320.0))

    def test_episode_without_name_uses_local_date(self):
        set_tz('America/New_York')
        (ep,) = series_rows(self.rpc, 'News')
        self.assertEqual(ep.label, '2026-09-01 14:00')  # Kodi gives recording times in UTC
        self.assertEqual(ep.date, '2026-09-01 14:00')
        self.assertEqual(ep.channel, 'BBC One')
        self.assertEqual(ep.playcount, 1)


    def test_untitled_recordings(self):
        recs = [
            {'recordingid': 7, 'title': 'Nova', 'showtitle': 'Untitled',
             'starttime': '2026-09-05 20:00:00', 'season': 3, 'episode': 4},
            {'recordingid': 8, 'title': 'Nova', 'showtitle': '',
             'starttime': '2026-09-06 20:00:00', 'season': -1, 'episode': -1},
            {'recordingid': 9, 'title': 'Nova', 'showtitle': 'Black Holes',
             'starttime': '2026-09-07 20:00:00', 'season': 3, 'episode': 6},
        ]
        rpc = FakeRpc({'PVR.GetRecordings': lambda p: {'recordings': recs}})
        eps = series_rows(rpc, 'Nova')
        self.assertEqual([e.untitled for e in eps], [True, True, False])
        self.assertEqual(eps[0].label, '2026-09-05 20:00')  # never "Untitled"
        self.assertEqual(eps[0].title, 'Nova')


    def test_recording_groups_from_the_directory(self):
        recs = [
            {'recordingid': 1, 'title': 'Alone', 'directory': 'Saved for Later/Alone'},
            {'recordingid': 2, 'title': '[COLOR yellow]Alone[/COLOR]',
             'directory': 'Saved for Later/Alone', 'showtitle': 'Damaged'},
            {'recordingid': 3, 'title': 'Alone', 'directory': 'Emily/Alone'},
            {'recordingid': 4, 'title': 'Scrubs', 'directory': 'Scrubs'},  # root default group
            {'recordingid': 5, 'title': 'News', 'directory': 'Default'},   # no title folders
        ]
        self.assertEqual([pvr.group_of(r) for r in recs],
                         ['Saved for Later', 'Saved for Later', 'Emily', 'Default', 'Default'])
        self.assertEqual(pvr.groups(recs), ['Default', 'Emily', 'Saved for Later'])
        self.assertEqual(len(pvr.in_group(recs, 'Default')), 2)
        # with the root default group setting off, Default is a folder like the others
        self.assertEqual(pvr.group_of({'title': 'Scrubs', 'directory': 'Default/Scrubs'}),
                         'Default')
        self.assertEqual(pvr.groups([{'title': 'Zed', 'directory': 'Zed'},
                                     {'title': 'A', 'directory': 'Alpha/A'}]),
                         ['Default', 'Alpha'])
        self.assertEqual(len(pvr.in_group(recs, None)), 5)
        saved = pvr.in_group(recs, 'Saved for Later')
        (alone,) = pvr.series_entries(saved)
        self.assertEqual((alone.display_title, alone.count), ('Alone', 2))
        damaged = next(e for e in series_rows(FakeRpc({}), 'Alone', saved)
                       if e.play == {'recordingid': 2})
        self.assertEqual(damaged.label, '[COLOR yellow]Damaged[/COLOR]')


class Library(unittest.TestCase):
    def test_show_with_seasons_lists_seasons_specials_last(self):
        rpc = FakeRpc({'VideoLibrary.GetSeasons': lambda p: {'seasons': [
            {'season': 0, 'label': 'Specials', 'episode': 2, 'watchedepisodes': 0},
            {'season': 2, 'label': 'Season 2', 'episode': 10, 'watchedepisodes': 3},
            {'season': 1, 'label': 'Season 1', 'episode': 6, 'watchedepisodes': 6},
        ]}})
        rows = library.rows(rpc, entry(LIBRARY, SHOW, {'tvshowid': 4}),
                            season_word='{} of {} watched')
        self.assertEqual([r.label for r in rows], ['Season 1', 'Season 2', 'Specials'])
        self.assertTrue(all(r.is_folder for r in rows))
        self.assertEqual(rows[1].browse, {'tvshowid': 4, 'season': 2})
        self.assertEqual((rows[0].playcount, rows[1].playcount), (1, 0))
        self.assertEqual(rows[1].label2, '3 of 10 watched')

    def test_opening_a_season(self):
        def get_episodes(p):
            self.assertEqual((p['tvshowid'], p['season']), (4, 1))
            return {'episodes': [
                {'episodeid': 2, 'title': 'B', 'season': 1, 'episode': 2},
                {'episodeid': 1, 'title': 'A', 'season': 1, 'episode': 1,
                 'resume': {'position': 10, 'total': 100}},
            ]}
        rpc = FakeRpc({'VideoLibrary.GetEpisodes': get_episodes})
        rows = library.rows(rpc, entry(LIBRARY, SHOW, {'tvshowid': 4}),
                            browse={'tvshowid': 4, 'season': 1})
        self.assertEqual([r.label for r in rows], ['A', 'B'])
        self.assertEqual((rows[0].play, rows[0].resume), ({'episodeid': 1}, 10.0))

    def test_single_season_show_goes_straight_to_episodes(self):
        rpc = FakeRpc({
            'VideoLibrary.GetSeasons': lambda p: {'seasons': [{'season': 1, 'label': 'Season 1'}]},
            'VideoLibrary.GetEpisodes': lambda p: {'episodes': [
                {'episodeid': 1, 'title': 'A', 'season': 1, 'episode': 1}]},
        })
        rows = library.rows(rpc, entry(LIBRARY, SHOW, {'tvshowid': 4}))
        self.assertEqual([r.label for r in rows], ['A'])
        self.assertNotIn('season', rpc.calls[1][1])

    def test_season_entry_lists_its_episodes(self):
        rpc = FakeRpc({'VideoLibrary.GetEpisodes': lambda p: {'episodes': []}})
        library.rows(rpc, entry(LIBRARY, SEASON, {'tvshowid': 4, 'season': 2}))
        self.assertEqual(rpc.calls[0][1]['season'], 2)

    def test_movie_is_a_single_row(self):
        rpc = FakeRpc({'VideoLibrary.GetMovieDetails': lambda p: {'moviedetails': {
            'movieid': 7, 'title': 'Film', 'playcount': 2}}})
        (ep,) = library.rows(rpc, entry(LIBRARY, MOVIE, {'movieid': 7}))
        self.assertEqual((ep.label, ep.play, ep.media_type, ep.playcount),
                         ('Film', {'movieid': 7}, 'movie', 2))

    def test_missing_show_raises(self):
        rpc = FakeRpc({'VideoLibrary.GetSeasons': lambda p: RpcError('Invalid params.')})
        with self.assertRaises(RpcError):
            library.rows(rpc, entry(LIBRARY, SHOW, {'tvshowid': 99}))

    def test_parent_lookups(self):
        rpc = FakeRpc({'VideoLibrary.GetEpisodeDetails': lambda p: {'episodedetails': {
            'tvshowid': 4, 'season': 1, 'showtitle': 'The Office'}}})
        self.assertEqual(library.episode_parent(rpc, 90), (4, 1, 'The Office'))


def directory(listing):
    """Files.GetDirectory handler over {path: [items]}."""
    def handler(p):
        if p['directory'] not in listing:
            return RpcError('Invalid params.')
        return {'files': listing[p['directory']]}
    return handler


def ep(path, label, **kw):
    return dict(file=path, filetype='file', label=label, type='episode', **kw)


def folder(path, label):
    return {'file': path, 'filetype': 'directory', 'label': label, 'type': 'unknown'}


class Addon(unittest.TestCase):
    def test_listing_is_shown_as_is(self):
        rpc = FakeRpc({'Files.GetDirectory': directory({'p://show': [
            ep('p://e1', 'Pilot', title='Pilot', season=1, episode=1),
            ep('p://e2', 'Two', title='Two', season=1, episode=2),
            folder('p://next', 'Next page'),
        ]})})
        rows = addon.rows(rpc, entry(ADDON, SHOW, {'path': 'p://show'}), 21)
        self.assertEqual([r.label for r in rows], ['Pilot', 'Two', 'Next page'])
        self.assertEqual(rows[0].play, {'file': 'p://e1'})
        self.assertEqual((rows[2].is_folder, rows[2].browse), (True, {'path': 'p://next'}))
        self.assertEqual(rpc.calls[0][1]['media'], 'video')

    def test_untitled_items_are_flagged(self):
        rpc = FakeRpc({'Files.GetDirectory': directory({'p://show': [
            ep('p://e1', 'Untitled', title='Untitled', season=1, episode=1),
            ep('p://e2', 'Two', title='Two', season=1, episode=2),
        ]})})
        rows = addon.rows(rpc, entry(ADDON, SHOW, {'path': 'p://show'}), 21)
        self.assertEqual([r.untitled for r in rows], [True, False])

    def test_kodi_22_asks_for_library_lookup(self):
        rpc = FakeRpc({'Files.GetDirectory': directory({'p://show': []})})
        addon.rows(rpc, entry(ADDON, SHOW, {'path': 'p://show'}), 22)
        self.assertEqual(rpc.calls[0][1]['media'], 'files')
        self.assertIn('playcount', rpc.calls[0][1]['properties'])

    def test_seasons_are_folders_opened_one_at_a_time(self):
        rpc = FakeRpc({'Files.GetDirectory': directory({
            'p://show': [folder('p://s1', 'Season 1'), folder('p://s2', 'Season 2')],
            'p://s2': [ep('p://c', 'Gamma', season=2, episode=1)],
        })})
        show = entry(ADDON, SHOW, {'path': 'p://show'})
        seasons = addon.rows(rpc, show, 21)
        self.assertEqual([r.label for r in seasons], ['Season 1', 'Season 2'])
        self.assertEqual(len(rpc.calls), 1)  # no season was listed yet
        (gamma,) = addon.rows(rpc, show, 21, browse=seasons[1].browse)
        self.assertEqual(gamma.label, 'Gamma')

    def test_a_lone_folder_is_opened_automatically(self):
        rpc = FakeRpc({'Files.GetDirectory': directory({
            'p://show': [folder('p://s1', 'Season 1')],
            'p://s1': [ep('p://a', 'Alpha'), ep('p://b', 'Beta')],
        })})
        rows = addon.rows(rpc, entry(ADDON, SHOW, {'path': 'p://show'}), 21)
        self.assertEqual([r.label for r in rows], ['Alpha', 'Beta'])

    def test_back_folders_are_dropped_at_the_top_level_only(self):
        backs = [folder('p://up1', '..'), folder('p://up2', '[B]<< Back[/B]'),
                 folder('p://up3', '.. Back')]
        rpc = FakeRpc({'Files.GetDirectory': directory({
            'p://show': backs + [folder('p://s1', 'Season 1'), folder('p://s2', 'Season 2'),
                                 folder('p://b2f', 'Back to the Future')],
            'p://s1': backs + [ep('p://a', 'Alpha')],
        })})
        show = entry(ADDON, SHOW, {'path': 'p://show'})
        top = addon.rows(rpc, show, 21)
        self.assertEqual([r.label for r in top], ['Season 1', 'Season 2', 'Back to the Future'])
        inner = addon.rows(rpc, show, 21, browse=top[0].browse)
        self.assertEqual([r.label for r in inner], ['..', '[B]<< Back[/B]', '.. Back', 'Alpha'])

    def test_a_lone_folder_beside_a_back_folder_is_opened(self):
        rpc = FakeRpc({'Files.GetDirectory': directory({
            'p://show': [folder('p://up', '..'), folder('p://s1', 'Season 1')],
            'p://s1': [folder('p://show', 'Back'), ep('p://a', 'Alpha')],
        })})
        rows = addon.rows(rpc, entry(ADDON, SHOW, {'path': 'p://show'}), 21)
        self.assertEqual([r.label for r in rows], ['Alpha'])

    def test_single_item_needs_no_call(self):
        e = entry(ADDON, ITEM, {'path': 'p://e1'}, title='Show - Pilot', plot='x')
        (only,) = addon.rows(None, e, 21)
        self.assertEqual((only.label, only.play, only.plot), ('Show - Pilot', {'file': 'p://e1'}, 'x'))

    def test_peek_show_title_looks_one_level_down(self):
        rpc = FakeRpc({'Files.GetDirectory': directory({
            'p://show': [folder('p://s1', 'Season 1')],
            'p://s1': [ep('p://a', 'Alpha', showtitle='The Office')],
        })})
        self.assertEqual(addon.peek_show_title(rpc, 'p://show', 21), 'The Office')

    def test_broken_folder_raises(self):
        rpc = FakeRpc({'Files.GetDirectory': directory({})})
        with self.assertRaises(RpcError):
            addon.rows(rpc, entry(ADDON, SHOW, {'path': 'p://gone'}), 21)


class Catalog(unittest.TestCase):
    def test_rows_sorted_ignoring_articles_and_mixed_across_sources(self):
        rows = catalog.rows(
            [entry(LIBRARY, SHOW, {'tvshowid': 1}, 'The Wire', added=3),
             entry(ADDON, SHOW, {'path': 'p://a'}, 'An Idiot Abroad', added=1)],
            [entry(PVR, SHOW, {'title': 'Panorama'}, 'Panorama', added=2)])
        self.assertEqual([e.display_title for e in rows],
                         ['An Idiot Abroad', 'Panorama', 'The Wire'])
        rows = catalog.rows(rows, [], catalog.SORT_ADDED)
        self.assertEqual([e.display_title for e in rows],
                         ['The Wire', 'Panorama', 'An Idiot Abroad'])

    def test_rows_for_a_group(self):
        stored = [entry(ADDON, SHOW, {'path': 'p://a'}, 'Everyone'),
                  entry(ADDON, SHOW, {'path': 'p://b'}, 'Emily only', group='Emily'),
                  entry(ADDON, SHOW, {'path': 'p://c'}, 'Bryan only', group='Bryan')]
        pick = lambda group: [e.display_title for e in catalog.rows(stored, [], group=group)]
        self.assertEqual(pick(None), ['Bryan only', 'Emily only', 'Everyone'])
        self.assertEqual(pick('Emily'), ['Emily only', 'Everyone'])
        self.assertEqual(pick(''), ['Everyone'])

    def test_movies_gathered_into_one_title_per_group(self):
        stored = [entry(LIBRARY, MOVIE, {'movieid': 1}, 'Up', added=5),
                  entry(ADDON, MOVIE, {'path': 'p://m'}, 'The Abyss', added=9, group='Emily'),
                  entry(LIBRARY, MOVIE, {'movieid': 2}, 'Heat', added=1, group='Bryan'),
                  entry(ADDON, SHOW, {'path': 'p://s'}, 'Nova')]
        loose = catalog.rows(stored, [], group='Emily')
        self.assertEqual([e.display_title for e in loose], ['The Abyss', 'Nova', 'Up'])
        rows = catalog.rows(stored, [], group='Emily', movies_title='Movies')
        self.assertEqual([e.display_title for e in rows], ['Movies', 'Nova'])
        movies = rows[0]
        self.assertEqual((movies.id, movies.source), (MOVIES_ID, MOVIES))
        self.assertEqual([m.display_title for m in movies.members], ['The Abyss', 'Up'])
        self.assertEqual(movies.added, 9)
        self.assertEqual(movies.to_dict().get('members'), None)
        self.assertEqual([e.display_title for e in catalog.rows(stored[3:], [], movies_title='M')],
                         ['Nova'])  # no movies, no "Movies" title

    def test_movie_rows(self):
        def details(p):
            if p['movieid'] != 1:
                return RpcError('Invalid params.')
            return {'moviedetails': {'title': 'Up (2009)', 'playcount': 1, 'art': {}}}
        rpc = FakeRpc({'VideoLibrary.GetMovieDetails': details})
        stored = [entry(LIBRARY, MOVIE, {'movieid': 1}, 'Up'),
                  entry(LIBRARY, MOVIE, {'movieid': 2}, 'Gone'),
                  entry(ADDON, MOVIE, {'path': 'p://m'}, 'The Abyss')]
        (movies,) = catalog.rows(stored, [], movies_title='Movies')
        rows = catalog.load_rows(rpc, movies, 21)
        self.assertEqual([(r.label, r.entry_id) for r in rows],
                         [('The Abyss', 'addon:movie:p://m'), ('Gone', 'library:movie:2'),
                          ('Up', 'library:movie:1')])
        self.assertEqual(rows[2].playcount, 1)
        self.assertEqual(rows[1].play, {})  # gone from the library: still listed, to remove it
        self.assertEqual([r.label for r in catalog.arrange(rows)], ['The Abyss', 'Gone', 'Up'])

    def test_arrange_keeps_folders_in_place(self):
        from model import Episode
        rows = [Episode('e1', {}, sort=(0,)), Episode('e2', {}, playcount=1, sort=(1,)),
                Episode('e3', {}, sort=(2,)), Episode('Next page', {}, is_folder=True, sort=(3,))]
        self.assertEqual([e.label for e in catalog.arrange(rows, newest_first=True)],
                         ['e3', 'e2', 'e1', 'Next page'])
        self.assertEqual([e.label for e in catalog.arrange(rows, hide_watched=True)],
                         ['e1', 'e3', 'Next page'])

    def test_dispatch(self):
        rpc = FakeRpc({'PVR.GetRecordings': lambda p: {'recordings': RECORDINGS}})
        newest = pvr.newest_entry([entry(PVR, SHOW, {'title': 'News'}, 'News')], 'N')
        self.assertEqual(len(catalog.load_rows(rpc, newest, 21)), 1)


if __name__ == '__main__':
    unittest.main()

# -*- coding: utf-8 -*-
"""Kodi's video library: TV shows, seasons, episodes and movies, by database id.

A show lists its seasons (or, with only one season, that season's episodes straight away); a
season row opens its episodes in place.
"""
from model import SHOW, SEASON, MOVIE
from sources.common import episode_from_item, folder_from_item, as_int

EPISODE_PROPS = ['title', 'plot', 'art', 'season', 'episode', 'playcount', 'resume', 'runtime',
                 'firstaired', 'showtitle', 'tvshowid']
SEASON_PROPS = ['season', 'showtitle', 'art', 'playcount', 'episode', 'watchedepisodes']
MOVIE_PROPS = ['title', 'plot', 'art', 'playcount', 'resume', 'runtime', 'premiered', 'year']


def _specials_last(season):
    return (1 if season == 0 else 0, season)


def _episode_sort(item):
    return _specials_last(as_int(item.get('season'))) + (as_int(item.get('episode')),)


def _episodes(rpc, tvshowid, season=None):
    params = {'tvshowid': tvshowid, 'properties': EPISODE_PROPS}
    if season is not None:
        params['season'] = season
    items = rpc.call('VideoLibrary.GetEpisodes', **params).get('episodes') or []
    return [episode_from_item(i, {'episodeid': i['episodeid']}, _episode_sort(i))
            for i in sorted(items, key=_episode_sort)]


def _season_row(item, tvshowid, season_word):
    season = as_int(item.get('season'))
    total = as_int(item.get('episode'), 0)
    watched = as_int(item.get('watchedepisodes'), 0)
    row = folder_from_item(item, {'tvshowid': tvshowid, 'season': season},
                           _specials_last(season), media_type='season')
    if total and watched >= total:
        row.playcount = 1
    row.label2 = season_word.format(watched, total) if total else ''
    return row


def rows(rpc, entry, browse=None, season_word='{}/{}'):
    ref = entry.ref
    if browse:
        return _episodes(rpc, browse['tvshowid'], browse['season'])
    if entry.kind == MOVIE:
        movie = rpc.call('VideoLibrary.GetMovieDetails', movieid=ref['movieid'],
                         properties=MOVIE_PROPS)['moviedetails']
        return [episode_from_item(movie, {'movieid': ref['movieid']}, (0,), media_type='movie')]
    if entry.kind == SEASON:
        return _episodes(rpc, ref['tvshowid'], ref['season'])
    if entry.kind == SHOW:
        seasons = rpc.call('VideoLibrary.GetSeasons', tvshowid=ref['tvshowid'],
                           properties=SEASON_PROPS).get('seasons') or []
        if len(seasons) <= 1:
            return _episodes(rpc, ref['tvshowid'])
        return [_season_row(s, ref['tvshowid'], season_word)
                for s in sorted(seasons, key=lambda s: _specials_last(as_int(s.get('season'))))]
    item = rpc.call('VideoLibrary.GetEpisodeDetails', episodeid=ref['episodeid'],
                    properties=EPISODE_PROPS)['episodedetails']
    return [episode_from_item(item, {'episodeid': ref['episodeid']}, _episode_sort(item))]


def episode_parent(rpc, episodeid):
    """(tvshowid, season, showtitle) of a library episode."""
    d = rpc.call('VideoLibrary.GetEpisodeDetails', episodeid=episodeid,
                 properties=['tvshowid', 'season', 'showtitle'])['episodedetails']
    return as_int(d.get('tvshowid')), as_int(d.get('season')), d.get('showtitle') or ''


def season_parent(rpc, seasonid):
    """(tvshowid, season, showtitle) of a library season."""
    d = rpc.call('VideoLibrary.GetSeasonDetails', seasonid=seasonid,
                 properties=['tvshowid', 'season', 'showtitle'])['seasondetails']
    return as_int(d.get('tvshowid')), as_int(d.get('season')), d.get('showtitle') or ''

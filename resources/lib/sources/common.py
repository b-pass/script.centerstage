# -*- coding: utf-8 -*-
from model import Episode, episode_code, is_untitled


def as_int(value, default=-1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def resume_of(item):
    r = item.get('resume') or {}
    return float(r.get('position') or 0), float(r.get('total') or 0)


def episode_label(title, season, episode, prefix=''):
    """The episode's row: its name alone (the details pane adds S01E02), or S01E02 without one."""
    parts = [p for p in (prefix, title or episode_code(season, episode)) if p]
    return ' · '.join(parts)


def folder_from_item(item, browse, sort, label=None, media_type=''):
    """A folder row (a season, or any add-on subfolder) that opens in place."""
    position, total = resume_of(item)
    return Episode(
        label=label or item.get('label') or item.get('title') or '', play={},
        title=item.get('title') or item.get('label') or '', season=as_int(item.get('season')),
        plot=item.get('plot') or '', art=dict(item.get('art') or {}),
        playcount=as_int(item.get('playcount'), 0), sort=sort, media_type=media_type,
        is_folder=True, browse=browse)


def episode_from_item(item, play, sort, prefix='', media_type='episode'):
    """Episode from a JSON-RPC item (library episode/movie, recording or directory entry)."""
    season = as_int(item.get('season'))
    number = as_int(item.get('episode'))
    title = item.get('title') or item.get('label') or ''
    position, total = resume_of(item)
    return Episode(
        label=episode_label(title, season, number, prefix) if media_type == 'episode' else title,
        play=play, title=title, season=season, episode=number, plot=item.get('plot') or '',
        art=dict(item.get('art') or {}), playcount=as_int(item.get('playcount'), 0),
        resume=position, total=total, runtime=as_int(item.get('runtime'), 0),
        date=item.get('firstaired') or item.get('premiered') or '', sort=sort,
        media_type=media_type, untitled=is_untitled(item.get('title') or item.get('label')))

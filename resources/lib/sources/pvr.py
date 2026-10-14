# -*- coding: utf-8 -*-
"""PVR recordings, grouped into one automatic entry per recording title.

Note Kodi's naming: for a recording, JSON-RPC "title" is the programme (show) name and "showtitle"
carries the backend's episode name (CPVRRecording maps strEpisodeName to m_strShowTitle). Season and
episode are -1 when the backend doesn't know them.

A recording's group is its "directory" without the trailing title folder. pvr.mythtv puts each
recording under "<recording group>/<title>" (just "<title>" for the Default group when its
"root default group" setting is on, which comes out as group ""). pvr.mythtv also wraps damaged
recordings' titles in [COLOR ...] tags; those are ignored when grouping by title.
"""
import calendar
import re
import time

from model import Entry, Episode, PVR, SHOW, entry_id, is_untitled, plain, pvr_key
from sources.common import as_int, resume_of, episode_label

RECORDING_PROPS = ['title', 'plot', 'plotoutline', 'playcount', 'resume', 'channel', 'starttime',
                   'runtime', 'art', 'icon', 'radio', 'isdeleted', 'season', 'episode',
                   'showtitle', 'directory']


def recordings(rpc):
    items = rpc.call('PVR.GetRecordings', properties=RECORDING_PROPS).get('recordings') or []
    return [r for r in items if not r.get('isdeleted') and not r.get('radio')
            and (r.get('title') or r.get('label'))]


def _title(rec):
    return ' '.join(plain(rec.get('title') or rec.get('label')).split())


def group_of(rec):
    parts = [p for p in (rec.get('directory') or '').split('/') if p]
    if parts and pvr_key(plain(parts[-1])) == pvr_key(_title(rec)):
        parts.pop()
    return '/'.join(parts)


def groups(recs):
    """The recording groups, alphabetically ("" for recordings outside any group last)."""
    return sorted({group_of(r) for r in recs}, key=lambda g: (not g, g.casefold()))


def in_group(recs, group):
    """The recordings in group; all of them when group is None."""
    return list(recs) if group is None else [r for r in recs if group_of(r) == group]


def _marked(rec, label):
    """label wrapped in the same formatting tags as the recording's title (pvr.mythtv colours
    damaged recordings)."""
    raw = (rec.get('title') or '').strip()
    opening = re.match(r'(?:\[[a-z]+[^\]]*\])+', raw, re.IGNORECASE)
    closing = re.search(r'(?:\[/[a-z]+\])+$', raw, re.IGNORECASE)
    return f'{opening.group()}{label}{closing.group()}' if opening and closing else label


def _art(rec):
    art = dict(rec.get('art') or {})
    if rec.get('icon') and not art.get('icon'):
        art['icon'] = rec['icon']
    if not art.get('thumb') and rec.get('icon'):
        art['thumb'] = rec['icon']
    return art


def _epoch(starttime):
    try:
        return float(calendar.timegm(time.strptime(starttime[:19], '%Y-%m-%d %H:%M:%S')))
    except (TypeError, ValueError):
        return 0.0


def _local(starttime):
    """JSON-RPC gives recording times in UTC (CPVRRecording::RecordingTimeAsUTC)."""
    epoch = _epoch(starttime)
    return time.strftime('%Y-%m-%d %H:%M', time.localtime(epoch)) if epoch else ''


def series_entries(recs, hidden=(), renames=None):
    """One Entry per recording title, newest recording's art and channel first."""
    renames = renames or {}
    groups = {}
    for rec in recs:
        groups.setdefault(pvr_key(_title(rec)), []).append(rec)
    out = []
    for key, group in groups.items():
        if key in hidden:
            continue
        group.sort(key=lambda r: r.get('starttime') or '', reverse=True)
        newest = group[0]
        title = _title(newest)
        eid = entry_id(PVR, SHOW, {'title': title})
        channels = sorted({r.get('channel') for r in group if r.get('channel')})
        art = _art(newest)
        if not art.get('poster') and art.get('thumb'):
            art['poster'] = art['thumb']
        out.append(Entry(
            id=eid, source=PVR, kind=SHOW, ref={'title': title},
            display_title=renames.get(eid, title), show_title=title, art=art,
            plot=newest.get('plotoutline') or newest.get('plot') or '',
            added=_epoch(newest.get('starttime')), origin=', '.join(channels), auto=True,
            count=len(group)))
    return out


def episodes(rpc, entry, recs=None):
    if recs is None:
        recs = recordings(rpc)
    key = pvr_key(entry.ref['title'])
    mine = [r for r in recs if pvr_key(_title(r)) == key]
    mine.sort(key=lambda r: r.get('starttime') or '')
    out = []
    for rec in mine:
        season = as_int(rec.get('season'))
        number = as_int(rec.get('episode'))
        name = rec.get('showtitle') or ''
        untitled = is_untitled(name)
        when = _local(rec.get('starttime'))
        position, total = resume_of(rec)
        out.append(Episode(
            label=_marked(rec, episode_label(when if untitled else name, season, number)),
            play={'recordingid': rec['recordingid']}, title=_title(rec) if untitled else name,
            season=season, episode=number, plot=rec.get('plot') or rec.get('plotoutline') or '',
            art=_art(rec), playcount=as_int(rec.get('playcount'), 0), resume=position,
            total=total, runtime=as_int(rec.get('runtime'), 0), date=when,
            channel=rec.get('channel') or '', untitled=untitled,
            sort=(rec.get('starttime') or '',)))
    return out

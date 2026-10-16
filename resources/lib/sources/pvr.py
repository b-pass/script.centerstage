# -*- coding: utf-8 -*-
"""PVR recordings, grouped into one automatic entry per recording title.

Note Kodi's naming: for a recording, JSON-RPC "title" is the programme (show) name and "showtitle"
carries the backend's episode name (CPVRRecording maps strEpisodeName to m_strShowTitle). Season and
episode are -1 when the backend doesn't know them.

A recording's group is its "directory" without the trailing title folder. pvr.mythtv puts each
recording under "<recording group>/<title>", or just "<title>" for the Default group when its
"Show default recording group as root" setting is on (its default). Recordings outside any group
folder therefore belong to "Default", so the Default group has the same name either way (and for
backends without groups, every recording is in it). pvr.mythtv also wraps damaged recordings'
titles in [COLOR ...] tags; those are ignored when grouping by title.
"""
import calendar
import re
import time

from model import (Entry, Episode, NEWEST, NEWEST_ID, PVR, SHOW, entry_id, is_untitled, plain,
                   pvr_key)
from sources.common import as_int, resume_of, episode_label

DEFAULT_GROUP = 'Default'
NEWEST_LIMIT = 25  # rows in the "Newest" title

RECORDING_PROPS = ['title', 'plot', 'plotoutline', 'playcount', 'resume', 'channel', 'starttime',
                   'runtime', 'art', 'icon', 'radio', 'isdeleted', 'season', 'episode',
                   'showtitle', 'directory', 'file']


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
    return '/'.join(parts) or DEFAULT_GROUP


def groups(recs):
    """The recording groups: Default first, then the others alphabetically."""
    return sorted({group_of(r) for r in recs}, key=lambda g: (g != DEFAULT_GROUP, g.casefold()))


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
        # The title shows the series artwork, as the recordings window does with the left list
        # focused (Art(fanart)); the preview image ("thumb") is for its episodes.
        fanart = next((r['art']['fanart'] for r in group if (r.get('art') or {}).get('fanart')),
                      '')
        if fanart:
            art['fanart'] = art['thumb'] = fanart
        out.append(Entry(
            id=eid, source=PVR, kind=SHOW, ref={'title': title},
            display_title=renames.get(eid, title), show_title=title, art=art,
            plot=newest.get('plotoutline') or newest.get('plot') or '',
            added=_epoch(newest.get('starttime')), origin=', '.join(channels), auto=True,
            count=len(group), watched=sum(1 for r in group if as_int(r.get('playcount'), 0) > 0)))
    return out


def newest_entry(series, title):
    """The "Newest" title, from the DVR series being shown (series_entries' result): their
    recordings, newest first. Its art is the newest series'."""
    latest = max(series, key=lambda e: e.added)
    return Entry(id=NEWEST_ID, source=NEWEST, kind=SHOW,
                 ref={'titles': {pvr_key(e.ref['title']): plain(e.display_title) for e in series}},
                 display_title=title,
                 art=dict(latest.art), added=latest.added, auto=True,
                 count=sum(e.count for e in series), watched=sum(e.watched for e in series))


def episodes(rpc, entry, recs=None):
    if recs is None:
        recs = recordings(rpc)
    key = pvr_key(entry.ref['title'])
    mine = [r for r in recs if pvr_key(_title(r)) == key]
    mine.sort(key=lambda r: r.get('starttime') or '')
    return [_episode(rec, (rec.get('starttime') or '',)) for rec in mine]


def newest(rpc, entry, recs=None):
    """The "Newest" title's rows: the recordings of the series in entry.ref['titles'] (the
    ones shown, so hidden series stay out), newest first, each named with its series as the
    titles list shows it."""
    if recs is None:
        recs = recordings(rpc)
    names = entry.ref['titles']
    out = []
    for rec in recs:
        key = pvr_key(_title(rec))
        if key in names:
            ep = _episode(rec, (-_epoch(rec.get('starttime')), rec['recordingid']))
            ep.show = names[key]
            out.append(ep)
    return sorted(out, key=lambda e: e.sort)


def _episode(rec, sort):
    season = as_int(rec.get('season'))
    number = as_int(rec.get('episode'))
    name = rec.get('showtitle') or ''
    untitled = is_untitled(name)
    when = _local(rec.get('starttime'))
    position, total = resume_of(rec)
    return Episode(
        label=_marked(rec, episode_label(when if untitled else name, season, number)),
        play={'recordingid': rec['recordingid']}, title=_title(rec) if untitled else name,
        season=season, episode=number, plot=rec.get('plot') or rec.get('plotoutline') or '',
        art=_art(rec), playcount=as_int(rec.get('playcount'), 0), resume=position,
        total=total, runtime=as_int(rec.get('runtime'), 0), date=when,
        channel=rec.get('channel') or '', untitled=untitled, sort=sort)

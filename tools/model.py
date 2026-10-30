"""The act's history as the Diário da República gives it: every version of every provision, the day it took effect, and
the amending act the source names for it; and, from those, the act's text in force on each day.

The source gives two views. The amendment timeline lists each amending act with the provisions it added, changed,
repealed or suspended and the day each change took effect, and points to the provision version it made. The
consolidated text for a day lists every provision with the version the source shows for that day, and that version's
own in-force day. A provision version is the unit: the record takes each version's own day as the day it takes effect.
Where the source's text for a day shows a version that, by its own date, is not yet in force (a change printed early),
or omits one that by its date already is (a change printed late), the record follows the version dates, and the
difference is listed (see `adjustments`).
"""
from __future__ import annotations

import html
import re

import source

NO_DAY = '1900-01-01'      # the source's empty date
STATE = {6: 'em vigor', 4: 'revogado', 2: 'suspenso'}

TAG = re.compile(r'<br\s*/?>|<[^>]+>', re.I)
SPACE = re.compile(r'[ \t  -  ]+')
DROP = re.compile('[­​‌‍﻿]')


def clean_text(t: str) -> list[str]:
    """The source's text as paragraphs: line breaks (and <br/>) separate paragraphs; links keep their words; runs of
    spaces become one space; the padding the source puts at the end of lines and empty lines are dropped."""
    t = t.replace('\r\n', '\n').replace('\r', '\n')
    t = TAG.sub(lambda m: '\n' if m.group().lower().startswith('<br') else '', t)
    t = html.unescape(t)
    t = DROP.sub('', t)
    return [l for l in (SPACE.sub(' ', l).strip() for l in t.split('\n')) if l]


def clean_line(t: str) -> str:
    return ' '.join(clean_text(t or ''))


class Version:
    __slots__ = ('vid', 'fid', 'date', 'day', 'state', 'name', 'epigraph', 'kind', 'text', 'seen', 'pos', 'path',
                 'undated', 'note')

    def __init__(self, row: dict, seen: str, pos: int):
        fv, cf = row['FragmentoVersao'], row['ConsolidacaoFragmento']
        self.vid = fv['Id']
        self.fid = fv['FragmentoId']
        self.date = fv['DataEntradaVigor'][:10]
        self.state = fv['VersaoEstadoId']
        self.name = clean_line(fv['Tituo'] if isinstance(fv['Tituo'], str) else cf['Name'])
        self.epigraph = clean_line(fv['Epigrafe'])
        self.kind = fv['TipoFragmentoId']
        self.text = clean_text(fv['Texto'] or '')
        self.path = cf['FullName']
        self.seen = seen          # the first day whose consolidated text shows this version
        self.pos = pos
        self.day = None           # the day the record takes it to be in force
        self.undated = False
        self.note = ''

    def content(self) -> tuple:
        return (self.state, self.name, self.epigraph, tuple(self.text))


def ordinal_key(day: str, v: Version) -> tuple:
    return (v.day, v.seen, v.pos)


def load(act: dict, offline: bool) -> dict:
    """Everything the source says about one act: its record, its timeline and its text on every day a version takes
    effect (fetching the text for any new day a version names, until no new day turns up)."""
    rec = source.record(act, offline)
    legis = rec['DiplomaFrag']['DiplomaLegisId']
    tl = source.timeline(act, legis, offline)
    start = act['start']
    days = {start} | {x['DataEntradaVigor'] for m in tl for x in m['ModificacaoList']['List']
                      if x['DataEntradaVigor'] != NO_DAY}
    # Regional acts (scripts/portugal-azores-law): also the text on the retrieval day, so a provision the DR shows only
    # in its current text is in the record (on the first day the DR shows it).
    if act.get('today') and act['today'] >= start:
        days.add(act['today'])
    snaps: dict[str, dict] = {}
    while True:
        todo = sorted(d for d in days if d not in snaps and d >= start)
        if not todo:
            break
        snaps.update(source.texts_on(act, legis, todo, offline))
        for d in todo:
            for row in snaps[d]['data']['LegConsBase']['List']:
                day = row['FragmentoVersao']['DataEntradaVigor'][:10]
                if day != NO_DAY and day > start:
                    days.add(day)
    return {'record': rec, 'legis': legis, 'timeline': tl, 'snaps': snaps}


def rows_of(snap: dict) -> list[dict]:
    """The consolidated text of one day, provision by provision; the source sometimes lists the whole text more than once
    (the same provision versions repeated), so each provision is kept once, at its first place."""
    out, seen = [], {}
    for row in snap['data']['LegConsBase']['List']:
        fid = row['FragmentoVersao']['FragmentoId']
        if fid in seen:
            if seen[fid] != row['FragmentoVersao']['Id']:
                raise SystemExit(f'two versions of fragment {fid} in one day\'s text')
            continue
        seen[fid] = row['FragmentoVersao']['Id']
        out.append(row)
    return out


def history(act: dict, data: dict) -> dict:
    """Versions with their days, the amending acts and what each names, and the text in force on each day."""
    start = act['start']
    days = sorted(data['snaps'])
    versions: dict[str, Version] = {}
    members: dict[str, list[str]] = {}       # day -> fragment ids the source shows that day, in order
    shown: dict[str, dict[str, str]] = {}    # day -> fragment id -> version id the source shows that day
    for d in days:
        rows = rows_of(data['snaps'][d])
        members[d] = []
        shown[d] = {}
        for i, row in enumerate(rows):
            vid = row['FragmentoVersao']['Id']
            if vid not in versions:
                versions[vid] = Version(row, d, i)
            else:
                # Regional acts: the DR can print one version's words differently on different days (an old day's text
                # carrying the act's number line, say); the words are taken from the latest day that shows it, so the
                # record ends on the DR's current wording. Its first day (seen) and place are kept.
                newer = Version(row, d, i)
                versions[vid].name, versions[vid].epigraph, versions[vid].text = newer.name, newer.epigraph, newer.text
            v = versions[vid]
            members[d].append(v.fid)
            shown[d][v.fid] = vid
    # The amending acts and the versions each names.
    acts: dict[str, dict] = {}
    names: dict[str, list[tuple[str, str]]] = {}
    for m in data['timeline']:
        lid = m['DiplomaLegisId']
        if m['IsDiplomaOriginal']:
            continue
        acts[lid] = {'id': lid, 'title': clean_line(m['Title']).replace(' - 1.ª Série', ''), 'kind': m['TipoDiploma'],
                     'number': m['Numero'], 'published': m['DataPublicacao'][:10], 'summary': clean_line(m['SumarioDiplomaLegis']),
                     'link': source.SITE + m['LinkSitemap'], 'mods': m['ModificacaoList']['List']}
        for x in m['ModificacaoList']['List']:
            names.setdefault(x['FragmentoVersaoDestinoId'], []).append((lid, x['TipoModificacao']))
    # Regional acts: the DR prints an act's signatures (fragment kind 7) only in its newer texts. A signature no
    # amending act names is part of the act as published: it is shown from the first day, in its first version.
    backdated = set()
    if act.get('today'):
        for vid, v in list(versions.items()):
            if v.kind == 7 and v.seen != days[0] and vid not in names and all(
                    w.fid != v.fid or w.seen >= v.seen for w in versions.values()):
                for d in days:
                    if d >= v.seen:
                        break
                    members[d].append(v.fid)
                    shown[d][v.fid] = vid
                backdated.add(vid)
    # The day each version takes effect.
    first = days[0]
    for v in versions.values():
        if v.vid in backdated:
            v.day = start
            v.note = f'the DR prints this signature only from {v.seen}; it belongs to the act as published, so it is shown from its first day'
            continue
        if v.seen == first:
            v.day = start                           # the act as it first took effect
            if v.date not in (NO_DAY, start) and v.date > start:
                v.note = f'the source dates this version {v.date} but prints it in the original text'
        elif v.date == NO_DAY:
            # No date in the source. A correction (declaração de retificação) the DR names for it takes effect when it
            # is published, if the DR's text shows it only later; anything else from the first day its text shows it.
            v.undated = True
            fixes = sorted({acts[l]['published'] for l, t in names.get(v.vid, []) if l in acts and t == 'Retifica'})
            if len(fixes) == 1 and start <= fixes[0] < v.seen:
                v.day = fixes[0]
                v.note = f'undated in the DR; dated by the publication of the correction that the DR names for it'
            else:
                v.day = v.seen
                v.note = f'undated in the DR; dated by the first consolidated text that shows it ({v.seen})'
        else:
            v.day = max(v.date, start)
    # The text in force on each day: the fragments the source shows that day, each in its latest version that has
    # taken effect by then.
    by_frag: dict[str, list[Version]] = {}
    for v in versions.values():
        by_frag.setdefault(v.fid, []).append(v)
    for vs in by_frag.values():
        vs.sort(key=lambda v: (v.day, v.seen, v.pos))
    commit_days = sorted({v.day for v in versions.values()} | {start}
                         | ({d for d in days if d >= start} if act.get('today') else set()))
    # (regional acts: also every day whose text was read, so a provision the DR prints only later enters the record
    # on the first day the DR shows it)
    states: dict[str, dict[str, str]] = {}
    orders: dict[str, list[str]] = {}
    adjustments = []
    snap_days = days
    for d in commit_days:
        sd = max(x for x in snap_days if x <= d)         # the source's text for that day
        state = {}
        for fid in members[sd]:
            live = [v for v in by_frag[fid] if v.day <= d]
            if not live:
                adjustments.append({'day': d, 'fid': fid, 'kind': 'printed early (not yet in force)',
                                    'shown': shown[sd][fid], 'used': None})
                continue
            v = live[-1]
            state[fid] = v.vid
            if v.vid != shown[sd][fid]:
                adjustments.append({'day': d, 'fid': fid, 'kind': 'version by its own date',
                                    'shown': shown[sd][fid], 'used': v.vid})
        states[d] = state
        orders[d] = members[sd]
    return {'versions': versions, 'acts': acts, 'names': names, 'days': commit_days, 'states': states,
            'orders': orders, 'adjustments': adjustments, 'by_frag': by_frag, 'snap_days': snap_days, 'shown': shown}

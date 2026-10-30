"""The acts of one autonomous region read from the Diário da República, and the first in-force day of each.

Targets, in build order: the Political-Administrative Statute (the Lei that revised it last, whose consolidated text is
the Statute), then every Decreto Legislativo Regional the DR marks in force (vigencia VIGENTE) and keeps a finished
consolidated text of (consolidacaoEstado CONCLUDED), by year and number.

The first day: the DR's timeline lists no change for the original act, so the day the act first took effect is read
from its consolidated text as it stands on the retrieval day: each provision version there carries the day it took
effect (DataEntradaVigor), and the versions no amending act made are the original's. The earliest such day is the
act's first day. The DR leaves the original versions of most older acts undated; the day is then read from the act's
own entry-into-force article ("O presente diploma entra em vigor no dia seguinte ao da sua publicação", "... em 1 de
janeiro de 2025", ...), counted from its publication in the Diário da República. An act with neither starts at the
first day the DR dates any change to it, as the oldest version available; an act with none of these is left out (the
general rule changed over time and by place, continent or regions, and is not applied by guesswork).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata

import model
import source

TODAY = '2026-10-30'   # the retrieval day: the consolidated text is read as it stands on this day


def ascii_slug(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def number_parts(num: str) -> tuple[int, str]:
    """'14/2024/A' -> (2024, '014'); '15-A/2008/A' -> (2008, '015-a'); '3/95/A' -> (1995, '003')."""
    n, y = num.split('/')[:2]
    y = int(re.match(r'\d+', y).group())
    if y < 100:
        y += 1900 if y >= 76 else 2000
    m = re.match(r'(\d+)(.*)', n)
    return y, f'{int(m.group(1)):03d}' + (('-' + ascii_slug(m.group(2))) if ascii_slug(m.group(2)) else '')


def act_of(hit: dict, region: dict, statute: bool = False) -> dict:
    frag = str(hit['DiplomaFragmentadoId'])
    year = int(hit['ano'])
    tipo = ascii_slug(hit['tipo'])
    if statute:
        slug, short = 'estatuto', f'Estatuto ({region["code_short"]})'
    else:
        y, n = number_parts(hit['numero'])
        slug, short = f'dlr-{y}-{n}', f'DLR {hit["numero"]}'
    return {'tipo': tipo, 'key': f'{year}-{frag}', 'frag': frag, 'slug': slug, 'short': short, 'width': 3,
            'start_evidence': None, 'parts': 'auto', 'hit_id': str(hit['dbId']), 'numero': hit['numero'],
            'published': hit['dataPublicacao'][:10], 'sumario': model.clean_line(hit.get('sumario') or ''),
            'designacao': hit.get('designacao') or '', 'today': TODAY}


def targets(listing: dict, region: dict) -> list[dict]:
    out = []
    # The Statute is consolidated under the Lei that approved it (the oldest); later revising Leis may carry a
    # consolidation of their own articles only.
    for h in sorted(listing.get('statute', []), key=lambda h: h['dataPublicacao']):
        if h.get('DiplomaFragmentadoId') and h.get('consolidacaoEstado') == 'CONCLUDED':
            out.append(act_of(h, region, statute=True))
            break
    dl = [h for h in listing['dlr'].values() if h.get('vigencia') == 'VIGENTE' and h.get('DiplomaFragmentadoId')
          and h.get('consolidacaoEstado') == 'CONCLUDED']
    dl.sort(key=lambda h: number_parts(h['numero']))
    out += [act_of(h, region) for h in dl]
    return out


def first_day(act: dict, offline: bool) -> tuple[str, str]:
    """The day the act first took effect, and how it was found."""
    rec = source.record(act, offline)
    legis = rec['DiplomaFrag']['DiplomaLegisId']
    tl = source.timeline(act, legis, offline)
    made = {x['FragmentoVersaoDestinoId'] for m in tl if not m['IsDiplomaOriginal']
            for x in m['ModificacaoList']['List']}
    snap = source.text_on(act, legis, TODAY, offline)
    if not snap['data']['LegConsBase']['List']:
        raise SystemExit('the DR gives no consolidated text for this act (empty record)')
    days = sorted({r['FragmentoVersao']['DataEntradaVigor'][:10] for r in snap['data']['LegConsBase']['List']
                   if r['FragmentoVersao']['Id'] not in made and r['FragmentoVersao']['DataEntradaVigor'][:10] != model.NO_DAY})
    if days:
        return days[0], 'dr-original-versions'
    rows = snap['data']['LegConsBase']['List']
    texts = [' '.join(model.clean_text(r['FragmentoVersao']['Texto'] or '')) for r in rows
             if r['FragmentoVersao']['Id'] not in made]
    day, quote = clause_day(texts, act['published'])
    if day:
        act['start_quote'] = quote
        return day, 'own-clause'
    # No clause: the general rule of Lei n.º 74/98, artigo 2.º, in the wording the DR gives for the day of publication
    # (read from its consolidated text): in the Autonomous Regions, the 15th day after publication (n.º 3, until
    # 30 June 2006); from 1 July 2006 (Lei n.º 26/2006), the 5th day everywhere (n.º 2). Counted from the day after
    # publication. Only for acts published from 1 December 1998, when Lei n.º 74/98 was in force whatever its own day.
    pub = dt.date.fromisoformat(act['published'])
    if act['published'] >= '1998-12-01':
        n = 15 if act['published'] < '2006-07-01' else 5
        act['start_quote'] = (f'Lei n.º 74/98, artigo 2.º, n.º {3 if n == 15 else 2}: the {n}th day after publication '
                              f'in the Diário da República ({act["published"]}); the act fixes no day itself.')
        return (pub + dt.timedelta(days=n)).isoformat(), 'general-rule'
    # Neither: the record starts at the first day the DR does date (a later amendment), as the oldest version
    # available, naming the earlier acts.
    later = sorted({x['DataEntradaVigor'][:10] for m in tl if not m['IsDiplomaOriginal'] for x in m['ModificacaoList']['List']
                    if x['DataEntradaVigor'][:10] != model.NO_DAY and x['TipoModificacao'] != 'Nota'})
    if later:
        return later[0], 'oldest-dated'
    raise SystemExit('no in-force day: the DR dates no provision and no entry-into-force clause was read')


MONTHS = {m: i + 1 for i, m in enumerate(['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto',
                                          'setembro', 'outubro', 'novembro', 'dezembro'])}
SENT = re.compile(r'[^.;]*\bentra(?:m|rá|rão)? em vigor\b[^;]*?(?:\.(?=\s|$)|;|$)', re.I)
DATE = re.compile(r'\b(\d{1,2})(?:\.º)? de (' + '|'.join(MONTHS) + r') de (\d{4})\b', re.I)


def clause_day(texts: list[str], published: str) -> tuple[str | None, str]:
    """The day an act's own entry-into-force sentence names, counted from its publication. Only sentences about the
    whole act ("O presente diploma / decreto legislativo regional / A presente lei ... entra em vigor") count, and they
    must agree on one day."""
    pub = dt.date.fromisoformat(published)
    found: dict[str, str] = {}
    for t in texts:
        for m in SENT.finditer(t):
            s = m.group(0).strip()
            low = s.lower()
            if not re.search(r'\b(o present[e]|a presente|este|esta)\s+(diploma|decreto|lei)', low):
                continue
            if re.search(r'\b(artigo|n\.º|alínea|capítulo|exceção|excepção|salvo|com exceção|com excepção)\b', low.split(' entra')[0]):
                continue   # a sentence about some provisions only
            d = None
            if re.search(r'no dia (seguinte|imediato) ao da (sua )?publica', low):
                d = pub + dt.timedelta(days=1)
            elif re.search(r'(na data|no dia) da (sua )?publica', low):
                d = pub
            elif re.search(r'no (primeiro|1\.º) dia (útil )?do mês (seguinte|imediato) ao da (sua )?publica', low) and 'útil' not in low:
                d = dt.date(pub.year + (pub.month == 12), pub.month % 12 + 1, 1)
            else:
                ds = DATE.findall(s)
                if len(ds) == 1 and 'após' not in low and 'seguinte' not in low:
                    dd, mm, yy = ds[0]
                    d = dt.date(int(yy), MONTHS[mm.lower()], int(dd))
            if d:
                found[d.isoformat()] = s
    if len(found) == 1:
        day, s = next(iter(found.items()))
        return day, s
    return None, ''


def settle(act: dict, data: dict, offline: bool) -> dict:
    """When the DR's text on the act's first day is empty (its consolidation begins later, with a republication, say),
    the record starts at the first day whose text the DR gives, as the oldest version available."""
    if data['snaps'][act['start']]['data']['LegConsBase']['List']:
        return data
    days = sorted(d for d, s in data['snaps'].items() if s['data']['LegConsBase']['List'])
    act['start'], act['how'] = days[0], 'oldest-dated'
    return model.load(act, offline)

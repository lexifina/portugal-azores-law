"""The day-by-day history of one act from the Diário da República's consolidated text: copied from
scripts/portugal-law/build.py (names, rendering a day's text into files, and build_act), unchanged except that the act
record carries no hand-written evidence of its first in-force day (start_evidence is None for regional acts).
"""
from __future__ import annotations

import re
import unicodedata

import model
import source

# ---------------------------------------------------------------- names

def ascii_slug(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


ARTICLE = re.compile(r'Artigo\s+(\d+)\s*\.?\s*[º°o]?\s*(?:-\s*([A-Z]+))?\s*$', re.I)


def article_file(name: str, width: int) -> str | None:
    m = ARTICLE.match(name)
    if not m:
        return None
    return f'artigo-{int(m.group(1)):0{width}d}' + (f'-{m.group(2).lower()}' if m.group(2) else '')


def file_order(path: str) -> tuple:
    """The order of an act's files: the preamble, the articles by number, the signatures, other files by name."""
    name = path.rsplit('/', 1)[-1][:-3]
    if name == 'preambulo':
        return (0, 0, '')
    m = re.fullmatch(r'artigo-(\d+)(-[a-z]+)?', name)
    if m:
        suf = m.group(2) or ''
        return (1, int(m.group(1)), f'{len(suf):02d}{suf}')
    if name == 'assinatura':
        return (3, 0, '')
    return (2, 0, name)


# ---------------------------------------------------------------- rendering a day's text into files

FILE_KINDS = {11, 15, 7}       # article, the whole act (its preamble), signatures


def part_of(act: dict, path: str) -> str:
    """The folder (under the act's) of a fragment, from its place in the act: 'Diploma > Anexo > ...' is the annex."""
    bits = path.split(' > ')
    top = bits[1] if len(bits) > 1 else ''
    if act['parts'] == 'auto':   # regional acts: each annex ('Anexo', 'Anexo I', ...) in a folder of its own
        return ascii_slug(top) if re.match(r'(?i)anexo\b', top) else ''
    for k, folder in act['parts'].items():
        if k and (top == k or top.startswith(k + ' ')):
            return folder
    return act['parts']['']


def render(act: dict, frags: list[tuple[str, model.Version]]) -> dict[str, dict]:
    """Files of the act from its fragments in order: each article (and the preamble, and the signatures) is a file; the
    headings of the parts that begin before an article are '##' lines at the top of its file. Returns path -> {text,
    fids, label}."""
    files: dict[str, dict] = {}
    pending: dict[str, list[tuple[str, list[str]]]] = {}
    last: dict[str, str] = {}
    for fid, v in frags:
        if v.state == 4:
            continue                    # revoked: the provision leaves the text in force
        folder = part_of(act, v.path)
        base = f'{act["slug"]}/{folder}/' if folder else f'{act["slug"]}/'
        if v.kind in FILE_KINDS or v.text:
            if v.kind == 15:
                name, title = 'preambulo', ([f'# {v.epigraph}'] if v.epigraph else [])
            elif v.kind == 7:
                name, title = 'assinatura', []
            else:
                name = article_file(v.name, act['width']) or ascii_slug(v.name) or f'fragmento-{fid}'
                title = [f'# {v.name}'] + ([f'### {v.epigraph}'] if v.epigraph else [])
            path = base + name + '.md'
            if path in files:
                if act['parts'] != 'auto':
                    raise SystemExit(f'{act["slug"]}: two fragments for {path} ({files[path]["fids"]}, {fid})')
                # Regional acts: the DR's text for a day can show two provisions under one number (a renumbering it
                # carried back); the later one gets a file of its own, named with its DR fragment id.
                path = path[:-3] + f'-fragmento-{fid}.md'
            heads = pending.pop(folder, [])
            lines = [l for _, hl in heads for l in hl] + title
            if v.state == 2:
                lines.append('*(Suspenso)*')
            lines += v.text
            files[path] = {'lines': lines, 'fids': [h for h, _ in heads] + [fid], 'label': v.name if v.kind == 11 else
                           ('Preâmbulo' if v.kind == 15 else 'Assinatura' if v.kind == 7 else v.name)}
            last[folder] = path
        else:
            hl = [f'## {v.name}'] + ([f'## {v.epigraph}'] if v.epigraph else [])
            pending.setdefault(folder, []).append((fid, hl))
    for folder, heads in pending.items():   # headings after the last article of a part: at the end of that article
        if folder in last:
            f = files[last[folder]]
            f['lines'] += [l for _, hl in heads for l in hl]
            f['fids'] += [h for h, _ in heads]
        elif act['parts'] == 'auto':
            # Regional acts: a folder with headings only (an annex printed as "Anexo - ver documento original") gets a
            # file of its own, so its words are not lost.
            base = f'{act["slug"]}/{folder}/' if folder else f'{act["slug"]}/'
            path = base + 'cabecalhos.md'
            files[path] = {'lines': [l for _, hl in heads for l in hl], 'fids': [h for h, _ in heads],
                           'label': heads[0][1][0].lstrip('# ')}
    for f in files.values():
        f['text'] = '\n\n'.join(f['lines']) + '\n'
    return files


def merged_order(prev: list[str], new: list[str]) -> list[str]:
    """The new day's order, with fragments only the previous day had kept after their predecessor there."""
    out = list(new)
    have = set(new)
    for i, f in enumerate(prev):
        if f in have:
            continue
        j = i - 1
        while j >= 0 and prev[j] not in have:
            j -= 1
        at = out.index(prev[j]) + 1 if j >= 0 else 0
        out.insert(at, f)
        have.add(f)
    return out


# ---------------------------------------------------------------- one act: days, changes, causes

def label_list(labels: list[str]) -> str:
    return ', '.join(labels)


def build_act(act: dict, offline: bool) -> dict:
    data = model.load(act, offline)
    if act.get('today'):
        import region
        data = region.settle(act, data, offline)
    h = model.history(act, data)
    V = h['versions']
    acts = h['acts']
    rec = data['record']
    own = {'id': data['legis'], 'title': clean_title(rec['DiplomaLegis']['ConteudoTitle'], rec['DiplomaLegis']['Numero']),
           'kind': rec['TipoDiploma']['Tipo'], 'number': rec['DiplomaLegis']['Numero'],
           'published': rec['DiplomaLegis']['DataPublicacao'][:10], 'summary': model.clean_line(rec['DiplomaLegis']['Sumario']),
           'link': source.SITE + rec['DiplomaLegis']['LinkSitemap'], 'issuer': rec['DiplomaLegis']['Emissor']}
    for a in acts.values():
        a['issuer'] = ''
        if not a['number']:     # old declarations without a number: named with their day of publication
            a['title'] = f'{a["title"]} de {a["published"]}'
    if act['start_evidence'] and not any(act['start_evidence'][1] in ' '.join(v.text) for v in V.values()
                                         if v.name == act['start_evidence'][0]):
        raise SystemExit(f'{act["slug"]}: the sentence giving the day of entry into force is not in the DR text')
    # The acts with changes the DR dates to each day (notes aside).
    acts_by_day: dict[str, set[str]] = {}
    for lid, a in acts.items():
        for x in a['mods']:
            if x['TipoModificacao'] != 'Nota' and x['DataEntradaVigor'] != model.NO_DAY:
                acts_by_day.setdefault(x['DataEntradaVigor'], set()).add(lid)
    removal_names: dict[str, set[str]] = {}     # fragment -> acts the timeline names for eliminating or repealing it
    for lid, a in acts.items():
        for x in a['mods']:
            if x['TipoModificacao'] in ('Elimina', 'Revoga') and x['FragmentoVersaoDestinoId'] in V:
                removal_names.setdefault(V[x['FragmentoVersaoDestinoId']].fid, set()).add(lid)

    def causes(vid: str) -> list[str]:
        named = [(l, t) for l, t in h['names'].get(vid, []) if l in acts]
        real = sorted({l for l, t in named if t != 'Nota'})
        return real or sorted({l for l, _ in named})

    def cause_of(f: str, old: str | None, vid: str | None, d: str) -> tuple[str, str]:
        """The act a change of one fragment on day d is credited to, and why."""
        c = causes(vid) if vid else sorted(removal_names.get(f, set()))
        if len(c) == 1:
            return c[0], 'named'
        if len(c) > 1:
            return 'candidates:' + ','.join(c), 'two acts named'
        day_acts = sorted(acts_by_day.get(d, set()))
        dated = vid is None or (not V[vid].undated and V[vid].date == d)
        if dated and len(day_acts) == 1:
            return day_acts[0], 'date only'
        if dated and day_acts:
            return 'candidates:' + ','.join(day_acts), 'two acts that day'
        return 'unexplained', 'not named'

    commits = []
    problems = []
    start = act['start']
    first_snap = h['snap_days'][0]
    cur = {f: v for f, v in h['shown'][first_snap].items()}     # the act as the DR prints its original text
    order = h['orders'][start]
    files = render(act, [(f, V[cur[f]]) for f in order if f in cur])
    commits.append({'day': start, 'kind': 'start', 'files': files, 'changed': sorted(files, key=file_order),
                    'before': {}, 'law': own['id'], 'evidence': {}})
    prev_order = order
    for d in h['days']:
        target = h['states'][d]
        new_order = h['orders'][d]
        delta = [f for f in sorted(set(cur) | set(target)) if cur.get(f) != target.get(f)]
        group: dict[str, list[str]] = {}
        why: dict[str, str] = {}
        for f in delta:
            vid, old = target.get(f), cur.get(f)
            if vid and old and V[vid].content() == V[old].content():
                group.setdefault('same', []).append(f)
                continue
            g, w = cause_of(f, old, vid, d)
            group.setdefault(g, []).append(f)
            why[f] = w
        steps = sorted((g for g in group if g in acts), key=lambda l: (acts[l]['published'], int(l)))
        steps = steps + sorted(g for g in group if g.startswith('candidates:')) + ['unexplained'] * ('unexplained' in group)
        order_now = merged_order(prev_order, new_order)
        # New versions with the same words (the DR renews version ids at each revision) change nothing by themselves;
        # a provision that only moves (a new order of the parts) goes with the first commit of the day.
        for f in group.get('same', []):
            cur[f] = target[f]
        if not steps and render(act, [(f, V[cur[f]]) for f in order_now if f in cur]) != files:
            steps = ['unexplained']
            group['unexplained'] = []
        for g in steps:
            for f in group[g]:
                if f in target:
                    cur[f] = target[f]
                else:
                    cur.pop(f, None)
            before = files
            files = render(act, [(f, V[cur[f]]) for f in order_now if f in cur])
            changed = sorted({p for p in set(before) | set(files) if (before.get(p) or {}).get('text') !=
                              (files.get(p) or {}).get('text')}, key=file_order)
            if not changed:
                continue
            kind = 'law' if g in acts else 'candidates' if g.startswith('candidates:') else 'unexplained'
            # Why each file changed: the reasons of the fragments of this step that sit in it (a file whose own
            # fragments did not change took headings that moved with a provision of this step).
            evidence: dict[str, list[str]] = {}
            for p in changed:
                fids = set((files.get(p) or {}).get('fids', [])) | set((before.get(p) or {}).get('fids', []))
                rs = sorted({why[f] for f in group[g] if f in fids})
                evidence[p] = rs or ['headings moved']
            commits.append({'day': d, 'kind': kind, 'law': g if kind == 'law' else None,
                            'candidates': g.split(':', 1)[1].split(',') if kind == 'candidates' else [],
                            'files': files, 'before': before, 'changed': changed, 'evidence': evidence,
                            'versions': [target[f] for f in group[g] if f in target]})
            if kind != 'law':
                problems.append(f'{d} {kind}: {", ".join(changed[:6])}')
        files = render(act, [(f, V[cur[f]]) for f in new_order if f in cur])
        expected = render(act, [(f, V[target[f]]) for f in new_order if f in target])
        if set(cur) != set(target) or {p: x['text'] for p, x in files.items()} != {p: x['text'] for p, x in expected.items()}:
            raise SystemExit(f'{act["slug"]} {d}: the commits of the day do not add up to the text of the day')
        prev_order = new_order
    return {'act': act, 'h': h, 'data': data, 'acts': acts, 'own': own, 'commits': commits, 'problems': problems}


def clean_title(title: str, number: str) -> str:
    t = model.clean_line(title)
    return f'{t} n.º {number}' if number and number not in t else t


def law_email(a: dict) -> str:
    kind = a['link'].rstrip('/').split('/')[-2] if '/detalhe/' in a['link'] else ascii_slug(a['kind'])
    # Acts without a number (old declarations of rectification) are told apart by their day and the DR's id.
    num = ascii_slug(a['number'].replace('/', '-')) if a['number'] else f'{a["published"]}-{a["id"]}'
    return f'{kind}-{num}@diariodarepublica.invalid'



"""Step 2: apply the rules in config.py to data/raw/ and write data/events.tsv. Local only, runs in seconds.

Rules come in two groups. Early rules need only the language count and Wikidata types, so fetch.py
applies them before downloading anything else. Late rules need the dates and locations that are
downloaded only for events that pass the early rules.
"""
import bisect
import csv
import datetime
import re
from collections import Counter, defaultdict

import config as C
from locations import best_kind, points_for, spread_km

TODAY = datetime.date.today()
DATE = re.compile(r'^([+-]?\d+)-(\d\d)-(\d\d)')
PRECISION = {11: 'day', 10: 'month', 9: 'year'}


def read(name):
    path = C.RAW / name
    if path.exists():
        with open(path) as fh:
            yield from csv.DictReader(fh, delimiter='\t')


def fetched_ids(name):
    """IDs already queried for data/raw/<name> (tracked by fetch.py, including ones with no results)."""
    path = C.RAW / (name + '.done')
    return set(path.read_text().split()) if path.exists() else set()


def load_candidates():
    """Every candidate with its language count, types and categories: all the early rules need."""
    ev = {r['item']: dict(langs=int(r['sitelinks']), enwiki=r['enwiki'], types=set()) for r in read('candidates.tsv')}
    type_label, ancestors = {}, defaultdict(set)
    for r in read('types.tsv'):
        if r['item'] in ev:
            ev[r['item']]['types'].add(r['type'])
        type_label[r['type']] = r['typeLabel'] or r['type']
    for r in read('type_ancestors.tsv'):
        ancestors[r['type']].add(r['ancestor'])
    root_to_cat = {root: cat for cat, roots in C.CATEGORIES.items() for root in roots}
    for e in ev.values():
        e['type_labels'] = sorted(type_label[t] for t in e['types'])
        e['categories'] = {root_to_cat[a] for t in e['types'] for a in ancestors[t] if a in root_to_cat}
    return ev


def load_details(ev):
    """Add labels, dates and locations, which exist only for events fetch.py downloaded them for."""
    downloaded = fetched_ids('labels.tsv') & fetched_ids('dates.tsv') & fetched_ids('locations.tsv')
    for q, e in ev.items():
        e.update(downloaded=q in downloaded, label=e['enwiki'], description='', enwiki_bytes='',
                 dates=defaultdict(list), own=set(), borrowed=defaultdict(dict))
    for r in read('labels.tsv'):
        if r['item'] in ev:
            ev[r['item']].update(label=r['label'] or ev[r['item']]['enwiki'], description=r['description'])
    for r in read('enwiki_lengths.tsv'):
        if r['item'] in ev:
            ev[r['item']]['enwiki_bytes'] = r['bytes']
    for r in read('dates.tsv'):
        if r['item'] in ev and DATE.match(r['time']):  # "unknown value" dates are blank nodes, not times
            ev[r['item']]['dates'][r['prop']].append((r['time'], int(r['precision'])))

    location_classes, countries, location_ancestors = defaultdict(set), defaultdict(set), defaultdict(set)
    for r in read('location_type_ancestors.tsv'):
        location_ancestors[r['type']].add(r['ancestor'])
    for r in read('location_types.tsv'):
        location_classes[r['location']] |= location_ancestors[r['type']]
    for r in read('location_countries.tsv'):
        countries[r['location']].add(r['country'])
    for r in read('locations.tsv'):
        e = ev.get(r['item'])
        if e is None:
            continue
        if r['kind'] == 'own':
            e['own'].add(r['coord'])
            continue
        loc = e['borrowed'][r['kind']].setdefault(r['location'], dict(  # kind is the property, e.g. P276
            coords=set(), iso=False, continent=False, area=0.0,
            classes=location_classes[r['location']], countries=len(countries[r['location']])))
        loc['coords'].add(r['coord'])
        loc['iso'] |= bool(r['iso'])
        loc['continent'] |= bool(r['continent'])
        try:
            loc['area'] = max(loc['area'], float(r['area']))
        except ValueError:
            pass


def year(t):
    return int(DATE.match(t).group(1))


def pick_date(statements, latest=False):
    """Most precise statement wins; ties go to the earliest (or latest, for end dates)."""
    if not statements:
        return None
    return max(statements, key=lambda s: (s[1], year(s[0]) if latest else -year(s[0])))


def is_future(t, precision):
    y, m, d = (int(x) for x in DATE.match(t).groups())
    if y != TODAY.year:
        return y > TODAY.year
    if precision >= 11:
        return (m, d) > (TODAY.month, TODAY.day)
    if precision == 10:
        return m > TODAY.month
    return False


def first_failed(rules):
    return next((reason for failed, reason in rules if failed), None)


def language_cut(cats):
    """The lowest MIN_LANGS among an event's categories, or None if none of them qualifies."""
    cuts = [C.MIN_LANGS[c] for c in (cats or {'uncategorised'}) if C.MIN_LANGS[c] is not None]
    return min(cuts, default=None)


NOT_EVENTS = [dict(rule, types=re.compile(rule['types'], re.I) if 'types' in rule else None,
                   title=re.compile(rule['title'], re.I) if 'title' in rule else None)
              for rule in C.NOT_EVENTS]
GENERIC_TYPES = re.compile(C.GENERIC_TYPES, re.I)


def is_not_event(rule, q, e):
    """Whether one NOT_EVENTS rule matches (see config.py for what each field means)."""
    if e['categories'] & C.HISTORICAL and not rule.get('even_if_historical'):
        return False
    if 'items' in rule and q not in rule['items']:
        return False
    if 'category' in rule and rule['category'] not in e['categories']:
        return False
    if rule['title'] and not rule['title'].search(e['enwiki']):
        return False
    if rule['types']:
        labels = e['type_labels']
        if not any(rule['types'].search(l) for l in labels):
            return False
        if rule.get('every') and not all(rule['types'].search(l) or GENERIC_TYPES.match(l) for l in labels):
            return False
    return True


def early_reason(q, e):
    """Why an event is dropped based on its languages and types alone, or None if it passes."""
    cut = language_cut(e['categories'])
    if cut is None:
        return 'only in dropped categories (entertainment, eclipse)'
    if e['langs'] < cut:
        return f'fewer than {cut} languages'
    return next((rule['reason'] for rule in NOT_EVENTS if is_not_event(rule, q, e)), None)


def late_reason(start, pts):
    """Why an event that passed the early rules is dropped based on its dates and locations, or None."""
    return first_failed([
        (not start or start[1] < C.MIN_DATE_PRECISION, 'date vaguer than a year, or unknown'),
        (start and is_future(*start), 'in the future'),
        (not pts, 'no usable Earth coordinate'),
    ])


def trim(kept):
    """Drop low-language events whose article is short for their era and category (TRIM_* in config)."""
    def group(r):
        cats = r['categories'].split('|') if r['categories'] else []
        primary = next((c for c in C.CATEGORIES if c in cats), 'uncategorised')
        return primary, bisect.bisect_right(C.ERAS, year(r['date']))
    lengths = defaultdict(list)
    for r in kept:
        lengths[group(r)].append(int(r['enwiki_bytes'] or 0))
    for v in lengths.values():
        v.sort()

    def percentile(r):
        v = lengths[group(r)]
        return 100 * bisect.bisect_left(v, int(r['enwiki_bytes'] or 0)) / len(v)
    return [r for r in kept if r['langs'] > C.TRIM_MAX_LANGS or percentile(r) >= C.TRIM_PERCENTILE]


def main():
    ev = load_candidates()
    load_details(ev)
    removed, kept, not_downloaded = Counter(), [], 0
    for q, e in ev.items():
        reason = early_reason(q, e)
        if not reason and not e['downloaded']:
            not_downloaded += 1
            continue
        if not reason:
            start = pick_date(e['dates']['P585'] + e['dates']['P580'])
            end = pick_date(e['dates']['P582'], latest=True)
            source, pts = points_for(e['own'], e['borrowed'])
            reason = late_reason(start, pts)
        if reason:
            removed[reason] += 1
            continue
        kept.append(dict(
            qid=q, label=e['label'], description=e['description'], enwiki=e['enwiki'], langs=e['langs'],
            enwiki_bytes=e['enwiki_bytes'],
            date=start[0].split('T')[0], date_precision=start[1],
            end_date=end[0].split('T')[0] if end else '', end_precision=end[1] if end else '',
            categories='|'.join(sorted(e['categories'])), types='|'.join(e['type_labels']),
            where=best_kind(pts), source=source, n_points=len(pts), spread_km=spread_km(list(pts)),
            points='|'.join(f'{lon} {lat} {kind}' for (lon, lat), kind in sorted(pts.items())),
        ))

    trimmed = trim(kept)
    removed[f'short article for its era and category ({C.TRIM_MAX_LANGS} or fewer languages)'] = len(kept) - len(trimmed)
    kept = sorted(trimmed, key=lambda r: -r['langs'])
    with open(C.EVENTS_TSV, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(kept[0]), delimiter='\t', lineterminator='\n')
        w.writeheader()
        w.writerows(kept)

    print(f"candidates fetched {(C.RAW / 'FETCHED').read_text().strip()}: {len(ev):,}")
    for reason, n in removed.most_common():
        print(f'  - {n:>7,}  {reason}')
    if not_downloaded:
        print(f'  ! {not_downloaded:>7,}  pass the rules but have no details yet: run fetch.py')
    print(f'kept {len(kept):,} -> {C.EVENTS_TSV.relative_to(C.ROOT)}\n')
    for label, counter in (
        ('categories', Counter(c for r in kept for c in (r['categories'].split('|') if r['categories'] else ['(none)']))),
        ('date precision', Counter(PRECISION[r['date_precision']] for r in kept)),
        ('location', Counter(r['where'] for r in kept)),
    ):
        print(f'{label}: ' + ', '.join(f'{k} {v:,}' for k, v in counter.most_common()))


if __name__ == '__main__':
    main()

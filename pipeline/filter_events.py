"""Step 2: apply the rules in config.py to data/raw/ and write data/events.tsv. Local only, runs in seconds.

Rules come in two groups. Early rules need only the language count and Wikidata types, so fetch.py
applies them before downloading anything else. Late rules need the dates and locations that are
downloaded only for events that pass the early rules.
"""
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
        e.update(downloaded=q in downloaded, label=e['enwiki'], description='',
                 dates=defaultdict(list), own=set(), borrowed=defaultdict(dict))
    for r in read('labels.tsv'):
        if r['item'] in ev:
            ev[r['item']].update(label=r['label'] or ev[r['item']]['enwiki'], description=r['description'])
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


def early_reason(q, e):
    """Why an event is dropped based on its languages and types alone, or None if it passes."""
    cats, labels = e['categories'], e['type_labels']
    protected = bool(cats & C.HISTORICAL)
    big_sport = 'sport' in cats and e['langs'] >= C.SPORT_MIN_LANGS and not C.SPORT_EXCEPTION_EXCLUDES.search(e['enwiki'])
    only_noise = (any(C.DROP_IF_ONLY_TYPES.search(l) for l in labels)
                  and all(C.DROP_IF_ONLY_TYPES.search(l) or C.GENERIC_TYPES.match(l) for l in labels))
    return first_failed([
        (q in C.BLOCKLIST, 'blocklist'),
        (e['langs'] < C.MIN_LANGS, f'fewer than {C.MIN_LANGS} languages'),
        (any(C.DROP_ALWAYS_IF_ANY_TYPE.search(l) for l in labels), 'not real: myth, hypothetical, fan convention...'),
        (not protected and not big_sport and any(C.DROP_IF_ANY_TYPE.search(l) for l in labels),
         'type: draft, census, festival, pageant...'),
        (not protected and not big_sport and 'sport' in cats,
         f'sport under {C.SPORT_MIN_LANGS} languages, or a league season'),
        (not protected and 'legislative term' in labels and C.NUMBERED_TERM_TITLE.match(e['enwiki']),
         'numbered parliamentary term'),
        (not protected and cats & (C.DROPPED_CATEGORIES - {'sport'}), 'entertainment or eclipse'),
        (not protected and only_noise, 'not an event: award, trade fair, holiday, era...'),
    ])


def late_reason(start, pts):
    """Why an event that passed the early rules is dropped based on its dates and locations, or None."""
    return first_failed([
        (not start or start[1] < C.MIN_DATE_PRECISION, 'date vaguer than a year, or unknown'),
        (start and is_future(*start), 'in the future'),
        (not pts, 'no usable Earth coordinate'),
    ])


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
            date=start[0].split('T')[0], date_precision=start[1],
            end_date=end[0].split('T')[0] if end else '', end_precision=end[1] if end else '',
            categories='|'.join(sorted(e['categories'])), types='|'.join(e['type_labels']),
            where=best_kind(pts), source=source, n_points=len(pts), spread_km=spread_km(list(pts)),
            points='|'.join(f'{lon} {lat} {kind}' for (lon, lat), kind in sorted(pts.items())),
        ))

    kept.sort(key=lambda r: -r['langs'])
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

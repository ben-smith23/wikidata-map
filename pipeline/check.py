"""Step 4 (optional): list kept events whose data looks wrong, for fixing in config.py or on Wikidata.

Uses only data/events.tsv and the cache in data/raw/; nothing is downloaded. Each check prints its
suspects, worst first. Not everything listed is an error, so read before acting on it.
"""
import csv
import math
from collections import defaultdict

import config as C
import filter_events as F
from locations import parse_point

FAR_KM = 500       # own coordinate this far from every small place the event names is suspect
LONG_YEARS = 100   # spans longer than this are listed


def km(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(min(1, h)))


def points(r):
    return [(float(x), float(y)) for x, y, _ in (p.split(' ') for p in r['points'].split('|'))]


def show(title, rows, limit=60):
    print(f'\n## {title}: {len(rows)}')
    for r in rows[:limit]:
        print('  ' + ' | '.join(map(str, r)))
    if len(rows) > limit:
        print(f'  ... and {len(rows) - limit} more')


def own_far_from_named(events, locations):
    """Own coordinate far from every site or small region in the event's location/admin-area statements:
    catches sign flips, typos and namesakes (the Saratoga campaign placed in Kazakhstan)."""
    rows = []
    for r in events:
        if r['source'] != 'P625':
            continue
        named = [(l['locationLabel'], parse_point(l['coord'])) for l in locations[r['qid']]
                 if l['kind'] in C.LOCATION_SOURCES and not l['iso'] and not l['continent']
                 and (not l['area'] or float(l['area']) < C.LARGE_REGION_MIN_AREA)]
        named = [(n, p) for n, p in named if p]
        if named:
            d = min(km(o, p) for o in points(r) for _, p in named)
            if d > FAR_KM:
                rows.append((round(d), r['qid'], r['enwiki'], r['date'], ', '.join(n for n, _ in named[:3])))
    return sorted(rows, reverse=True)


def title_year_mismatch(events):
    """Year in the title still disagrees with the dates (the filter fixes most of these itself)."""
    rows = []
    for r in events:
        span = F.title_years(r['enwiki'])
        start, end = F.year(r['date']), F.year(r['end_date'] or r['date'])
        if span and not (span[0] - 1 <= end and start <= span[1] + 1):
            rows.append((r['qid'], r['enwiki'], r['date'], r['end_date']))
    return rows


def end_before_start(events):
    return [(r['qid'], r['enwiki'], r['date'], r['end_date']) for r in events
            if r['end_date'] and F.year(r['end_date']) < F.year(r['date'])]


def long_spans(events):
    rows = [(F.year(r['end_date']) - F.year(r['date']), r['qid'], r['enwiki'], r['categories'] or '-')
            for r in events if r['end_date']]
    return sorted((r for r in rows if r[0] > LONG_YEARS), reverse=True)


def duplicates(events):
    by_name = defaultdict(list)
    for r in events:
        by_name[(r['enwiki'], r['date'])].append(r['qid'])
    return [(name, date, *qs) for (name, date), qs in by_name.items() if len(qs) > 1]


def main():
    csv.field_size_limit(10 ** 8)
    events = list(csv.DictReader(open(C.EVENTS_TSV), delimiter='\t'))
    locations = defaultdict(list)
    for r in F.read('locations.tsv'):
        locations[r['item']].append(r)
    print(f'checking {len(events):,} events in {C.EVENTS_TSV.relative_to(C.ROOT)}')
    show(f'own coordinate over {FAR_KM} km from the places the event names', own_far_from_named(events, locations))
    show('year in the title disagrees with the dates', title_year_mismatch(events))
    show('ends before it starts', end_before_start(events))
    show(f'spans over {LONG_YEARS} years', long_spans(events))
    show('same article and date twice', duplicates(events))


if __name__ == '__main__':
    main()

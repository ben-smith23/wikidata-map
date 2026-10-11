"""Step 2: apply the rules in config.py to data/raw/ and write data/events.tsv. Local only, runs in seconds."""
import csv
import datetime
import math
import re
from collections import Counter, defaultdict

import config as C

TODAY = datetime.date.today()
DATE = re.compile(r'^([+-]?\d+)-(\d\d)-(\d\d)')
POINT = re.compile(r'^POINT\((\S+) (\S+)\)$')  # Earth coordinates only; other globes are prefixed with a URI
WHERE_ORDER = ['own', 'site', 'region', 'large_region', 'country', 'continent']


def read(name):
    with open(C.RAW / name) as fh:
        yield from csv.DictReader(fh, delimiter='\t')


def load():
    ev = {r['item']: dict(langs=int(r['sitelinks']), enwiki=r['enwiki']) for r in read('events.tsv')}
    for r in read('labels.tsv'):
        ev[r['item']].update(label=r['label'] or ev[r['item']]['enwiki'], description=r['description'])

    types, type_label = defaultdict(set), {}
    for r in read('types.tsv'):
        types[r['item']].add(r['type'])
        type_label[r['type']] = r['typeLabel'] or r['type']
    ancestors = defaultdict(set)
    for r in read('type_ancestors.tsv'):
        ancestors[r['type']].add(r['ancestor'])

    dates = defaultdict(lambda: defaultdict(list))
    for r in read('dates.tsv'):
        if DATE.match(r['time']):  # "unknown value" dates are blank nodes, not times
            dates[r['item']][r['prop']].append((r['time'], int(r['precision'])))

    own, borrowed = defaultdict(set), defaultdict(dict)
    for r in read('locations.tsv'):
        if r['kind'] == 'own':
            own[r['item']].add(r['coord'])
            continue
        loc = borrowed[r['item']].setdefault(r['location'], dict(
            label=r['locationLabel'] or r['location'], coords=set(), iso=False, continent=False, area=0.0))
        loc['coords'].add(r['coord'])
        loc['iso'] |= bool(r['iso'])
        loc['continent'] |= bool(r['continent'])
        try:
            loc['area'] = max(loc['area'], float(r['area']))
        except ValueError:
            pass

    # What kind of place each borrowed location is (all superclasses of its types) and its country count
    location_ancestors = defaultdict(set)
    for r in read('location_type_ancestors.tsv'):
        location_ancestors[r['type']].add(r['ancestor'])
    location_classes = defaultdict(set)
    for r in read('location_types.tsv'):
        location_classes[r['location']] |= location_ancestors[r['type']]
    countries = defaultdict(set)
    for r in read('location_countries.tsv'):
        countries[r['location']].add(r['country'])
    for locs in borrowed.values():
        for q, loc in locs.items():
            loc['classes'], loc['countries'] = location_classes[q], len(countries[q])
    return ev, types, type_label, ancestors, dates, own, borrowed


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


LOCATION_CLASSES = {kind: set(qids) for kind, qids in C.LOCATION_CLASSES.items()}


def location_kind(loc):
    """How vague a borrowed location is. Rule order is documented in config.py."""
    is_a = lambda kind: bool(loc['classes'] & LOCATION_CLASSES[kind])
    if loc['continent']:
        return 'continent'
    if loc['iso']:
        return 'site' if 0 < loc['area'] < C.REGION_MIN_AREA else 'country'
    if is_a('country'):
        return 'country'
    if is_a('site'):
        return 'site'
    if loc['area']:
        if loc['area'] > C.LARGE_REGION_MIN_AREA:
            return 'large_region'
        return 'region' if loc['area'] > C.REGION_MIN_AREA else 'site'
    if is_a('large_region'):
        return 'large_region'
    if is_a('region'):
        return 'region' if 1 <= loc['countries'] <= C.REGION_MAX_COUNTRIES else 'large_region'
    return 'site'


def parse_point(coord):
    m = POINT.match(coord)
    if not m:
        return None
    lon, lat = float(m.group(1)), float(m.group(2))
    return (round(lon, 5), round(lat, 5)) if -180 <= lon <= 180 and -90 <= lat <= 90 else None


def points_for(q, own, borrowed):
    """Own coordinates if the event has any usable ones, otherwise those of its locations."""
    pts = {p: 'own' for p in map(parse_point, own[q]) if p}
    if pts:
        return pts
    for loc in borrowed[q].values():
        kind = location_kind(loc)
        for p in filter(None, map(parse_point, loc['coords'])):
            # if two locations share a point, keep the more precise kind
            if p not in pts or WHERE_ORDER.index(kind) < WHERE_ORDER.index(pts[p]):
                pts[p] = kind
    return pts


def spread_km(points):
    def hav(a, b):
        lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
        h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        return 2 * 6371 * math.asin(math.sqrt(min(1, h)))
    return round(max((hav(a, b) for i, a in enumerate(points) for b in points[i + 1:]), default=0))


def main():
    ev, types, type_label, ancestors, dates, own, borrowed = load()
    root_to_cat = {root: cat for cat, roots in C.CATEGORIES.items() for root in roots}
    junk_types = {t for t, l in type_label.items() if C.JUNK_TYPE_LABELS.search(l)}
    ent_types = {t for t, l in type_label.items() if C.ENTERTAINMENT_TYPE_LABELS.search(l)}

    removed, kept = Counter(), []
    for q, e in ev.items():
        cats = {root_to_cat[a] for t in types[q] for a in ancestors[t] if a in root_to_cat}
        historical = bool(cats & C.HISTORICAL)
        big_sport = 'sport' in cats and e['langs'] >= C.SPORT_MIN_LANGS
        start = pick_date(dates[q]['P585'] + dates[q]['P580'])
        end = pick_date(dates[q]['P582'], latest=True)
        pts = points_for(q, own, borrowed)

        if q in C.BLOCKLIST:
            reason = 'blocklist'
        elif e['langs'] < C.MIN_LANGS:
            reason = f'fewer than {C.MIN_LANGS} languages'
        elif not start or start[1] < C.MIN_DATE_PRECISION:
            reason = 'date vaguer than a year (or unknown)'
        elif is_future(*start):
            reason = 'in the future'
        elif types[q] & junk_types and not historical:
            reason = 'junk type (draft, census, road...)'
        elif types[q] & ent_types and not historical and not big_sport:
            reason = 'festival / pageant / Eurovision'
        elif 'sport' in cats and not historical and not big_sport:
            reason = f'sport under {C.SPORT_MIN_LANGS} languages'
        elif cats & (C.DROPPED - {'sport'}) and not historical:
            reason = 'entertainment / eclipse'
        elif not pts:
            reason = 'no usable Earth coordinate'
        else:
            reason = None

        if reason:
            removed[reason] += 1
            continue
        kept.append(dict(
            qid=q, label=e['label'], description=e['description'], enwiki=e['enwiki'], langs=e['langs'],
            date=start[0][:start[0].index('T')], date_precision=start[1],
            end_date=end[0][:end[0].index('T')] if end else '', end_precision=end[1] if end else '',
            categories='|'.join(sorted(cats)), types='|'.join(sorted(type_label[t] for t in types[q])),
            where=min(pts.values(), key=WHERE_ORDER.index), n_points=len(pts), spread_km=spread_km(list(pts)),
            points='|'.join(f'{lon} {lat} {kind}' for (lon, lat), kind in sorted(pts.items())),
        ))

    kept.sort(key=lambda r: -r['langs'])
    with open(C.EVENTS_TSV, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(kept[0]), delimiter='\t', lineterminator='\n')
        w.writeheader()
        w.writerows(kept)

    fetched = (C.RAW / 'FETCHED').read_text().strip()
    print(f'raw data fetched {fetched}: {len(ev):,} events')
    for reason, n in removed.most_common():
        print(f'  - {n:>7,}  {reason}')
    print(f'kept {len(kept):,} -> {C.EVENTS_TSV.relative_to(C.ROOT)}\n')
    for label, counter in (
        ('categories', Counter(c for r in kept for c in (r['categories'].split('|') if r['categories'] else ['(none)']))),
        ('date precision', Counter({11: 'day', 10: 'month', 9: 'year'}[r['date_precision']] for r in kept)),
        ('location', Counter(r['where'] for r in kept)),
    ):
        print(f'{label}: ' + ', '.join(f'{k} {v:,}' for k, v in counter.most_common()))


if __name__ == '__main__':
    main()

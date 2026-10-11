"""Step 2: apply the rules in config.py to data/raw/ and write data/events.tsv. Local only, runs in seconds."""
import csv
import datetime
import re
from collections import Counter, defaultdict

import config as C
from locations import KINDS, points_for, spread_km

TODAY = datetime.date.today()
DATE = re.compile(r'^([+-]?\d+)-(\d\d)-(\d\d)')
PRECISION = {11: 'day', 10: 'month', 9: 'year'}


def read(name):
    with open(C.RAW / name) as fh:
        yield from csv.DictReader(fh, delimiter='\t')


def load():
    """Everything in data/raw/, keyed by event QID."""
    ev = {r['item']: dict(langs=int(r['sitelinks']), enwiki=r['enwiki'], types=set(), dates=defaultdict(list),
                          own=set(), borrowed={}) for r in read('candidates.tsv')}
    for r in read('labels.tsv'):
        ev[r['item']].update(label=r['label'] or ev[r['item']]['enwiki'], description=r['description'])

    type_label, ancestors = {}, defaultdict(set)
    for r in read('types.tsv'):
        ev[r['item']]['types'].add(r['type'])
        type_label[r['type']] = r['typeLabel'] or r['type']
    for r in read('type_ancestors.tsv'):
        ancestors[r['type']].add(r['ancestor'])

    for r in read('dates.tsv'):
        if DATE.match(r['time']):  # "unknown value" dates are blank nodes, not times
            ev[r['item']]['dates'][r['prop']].append((r['time'], int(r['precision'])))

    location_classes, countries, location_ancestors = defaultdict(set), defaultdict(set), defaultdict(set)
    for r in read('location_type_ancestors.tsv'):
        location_ancestors[r['type']].add(r['ancestor'])
    for r in read('location_types.tsv'):
        location_classes[r['location']] |= location_ancestors[r['type']]
    for r in read('location_countries.tsv'):
        countries[r['location']].add(r['country'])
    for r in read('locations.tsv'):
        e = ev[r['item']]
        if r['kind'] == 'own':
            e['own'].add(r['coord'])
            continue
        loc = e['borrowed'].setdefault(r['location'], dict(
            coords=set(), iso=False, continent=False, area=0.0,
            classes=location_classes[r['location']], countries=len(countries[r['location']])))
        loc['coords'].add(r['coord'])
        loc['iso'] |= bool(r['iso'])
        loc['continent'] |= bool(r['continent'])
        try:
            loc['area'] = max(loc['area'], float(r['area']))
        except ValueError:
            pass

    root_to_cat = {root: cat for cat, roots in C.CATEGORIES.items() for root in roots}
    for e in ev.values():
        e['type_labels'] = sorted(type_label[t] for t in e['types'])
        e['categories'] = {root_to_cat[a] for t in e['types'] for a in ancestors[t] if a in root_to_cat}
    return ev


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


def reject_reason(q, e, start, pts):
    """Why an event is dropped, or None to keep it. Rules are checked in order; the first match wins."""
    cats, labels = e['categories'], e['type_labels']
    protected = bool(cats & C.HISTORICAL)
    big_sport = 'sport' in cats and e['langs'] >= C.SPORT_MIN_LANGS and not C.SEASON_LABEL.match(e['label'])
    only_noise = (any(C.DROP_IF_ONLY_TYPES.search(l) for l in labels)
                  and all(C.DROP_IF_ONLY_TYPES.search(l) or C.GENERIC_TYPES.match(l) for l in labels))
    rules = [
        (q in C.BLOCKLIST, 'blocklist'),
        (e['langs'] < C.MIN_LANGS, f'fewer than {C.MIN_LANGS} languages'),
        (not start or start[1] < C.MIN_DATE_PRECISION, 'date vaguer than a year, or unknown'),
        (start and is_future(*start), 'in the future'),
        (not protected and not big_sport and any(C.DROP_IF_ANY_TYPE.search(l) for l in labels),
         'type: draft, census, festival, pageant...'),
        (not protected and not big_sport and 'sport' in cats, f'sport under {C.SPORT_MIN_LANGS} languages, or a league season'),
        (not protected and cats & (C.DROPPED_CATEGORIES - {'sport'}), 'entertainment or eclipse'),
        (not protected and only_noise, 'not an event: award, trade fair, holiday, era...'),
        (not pts, 'no usable Earth coordinate'),
    ]
    return next((reason for failed, reason in rules if failed), None)


def main():
    ev = load()
    removed, kept = Counter(), []
    for q, e in ev.items():
        start = pick_date(e['dates']['P585'] + e['dates']['P580'])
        end = pick_date(e['dates']['P582'], latest=True)
        pts = points_for(e['own'], e['borrowed'])
        reason = reject_reason(q, e, start, pts)
        if reason:
            removed[reason] += 1
            continue
        kept.append(dict(
            qid=q, label=e['label'], description=e['description'], enwiki=e['enwiki'], langs=e['langs'],
            date=start[0].split('T')[0], date_precision=start[1],
            end_date=end[0].split('T')[0] if end else '', end_precision=end[1] if end else '',
            categories='|'.join(sorted(e['categories'])), types='|'.join(e['type_labels']),
            where=min(pts.values(), key=KINDS.index), n_points=len(pts), spread_km=spread_km(list(pts)),
            points='|'.join(f'{lon} {lat} {kind}' for (lon, lat), kind in sorted(pts.items())),
        ))

    kept.sort(key=lambda r: -r['langs'])
    with open(C.EVENTS_TSV, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(kept[0]), delimiter='\t', lineterminator='\n')
        w.writeheader()
        w.writerows(kept)

    print(f"raw data fetched {(C.RAW / 'FETCHED').read_text().strip()}: {len(ev):,} candidate events")
    for reason, n in removed.most_common():
        print(f'  - {n:>7,}  {reason}')
    print(f'kept {len(kept):,} -> {C.EVENTS_TSV.relative_to(C.ROOT)}\n')
    for label, counter in (
        ('categories', Counter(c for r in kept for c in (r['categories'].split('|') if r['categories'] else ['(none)']))),
        ('date precision', Counter(PRECISION[r['date_precision']] for r in kept)),
        ('location', Counter(r['where'] for r in kept)),
    ):
        print(f'{label}: ' + ', '.join(f'{k} {v:,}' for k, v in counter.most_common()))


if __name__ == '__main__':
    main()

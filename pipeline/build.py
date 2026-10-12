"""Step 3: turn data/events.tsv into web/public/events.json, the compact file the map loads."""
import csv
import json
import re

import config as C


def display_name(enwiki_title):
    """The English Wikipedia title, so the name matches the article it links to, without a trailing
    disambiguator: "Eastern Front (World War II)" -> "Eastern Front"."""
    return re.sub(r' \([^()]*\)$', '', enwiki_title)


def main():
    with open(C.EVENTS_TSV) as fh:
        rows = list(csv.DictReader(fh, delimiter='\t'))
    events = []
    for r in rows:
        e = {
            'id': r['qid'],
            'name': display_name(r['enwiki']),
            'desc': r['description'],
            'wiki': r['enwiki'],
            'langs': int(r['langs']),
            'date': r['date'],
            'prec': int(r['date_precision']),
            'cats': r['categories'].split('|') if r['categories'] else [],
            'where': r['where'],
            'pts': [[float(lon), float(lat), kind] for lon, lat, kind in (p.split(' ') for p in r['points'].split('|'))],
        }
        if r['end_date']:
            e['end'], e['endPrec'] = r['end_date'], int(r['end_precision'])
        events.append(e)
    with open(C.EVENTS_JSON, 'w') as fh:
        json.dump(events, fh, ensure_ascii=False, separators=(',', ':'))
    print(f'wrote {len(events):,} events -> {C.EVENTS_JSON.relative_to(C.ROOT)} '
          f'({C.EVENTS_JSON.stat().st_size / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()

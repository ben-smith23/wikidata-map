"""Step 1: download from Wikidata (via QLever) only what the filter needs, into data/raw/.

  1. Candidates: every dated, located event with an English Wikipedia article. One small query,
     always re-run so new Wikidata events are picked up.
  2. Types, only for candidates with at least the lowest MIN_LANGS cut. The early rules (languages, types,
     categories) are then applied straight away.
  3. Labels, dates, locations and English Wikipedia article length, only for events that pass
     the early rules.

Everything after step 1 is incremental: each file has a <name>.done list of the IDs already
queried, and only new IDs are fetched. Loosening a rule downloads just the newly admitted events.
Pass --refresh to wipe the cache and download everything again.
"""
import csv
import datetime
import json
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import config as C
import filter_events as F
from sparql import BATCH_SIZE, query

OWN, BORROWED = 'P625', C.LOCATION_SOURCES + ([C.LOCATION_FALLBACK] if C.LOCATION_FALLBACK else [])

CANDIDATES = """
SELECT ?item (SAMPLE(?sl) AS ?sitelinks) (SAMPLE(?title) AS ?enwiki) WHERE {
  ?item wdt:P31/wdt:P279* wd:Q1190554 .
  ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
  ?item wikibase:sitelinks ?sl .
  { ?item wdt:P585 ?d } UNION { ?item wdt:P580 ?d }
  { ?item wdt:%s ?c } %s
} GROUP BY ?item
""" % (OWN, ' '.join(f'UNION {{ ?item wdt:{p} ?l . ?l wdt:{OWN} ?c }}' for p in BORROWED))
# (QLever silently returns nothing for FILTER(?sl >= n), so the language cut happens locally.)

TYPES = """
SELECT ?item ?type ?typeLabel WHERE { VALUES ?item { {VALUES} }
  ?item wdt:P31 ?type .
  OPTIONAL { ?type rdfs:label ?typeLabel FILTER(LANG(?typeLabel) = "en") }
}
"""

# Full superclass chain of every type, so categories can be redefined locally.
TYPE_ANCESTORS = """
SELECT DISTINCT ?type ?ancestor WHERE { VALUES ?type { {VALUES} }
  ?type wdt:P279* ?ancestor .
}
"""

LABELS = """
SELECT ?item ?label ?description WHERE { VALUES ?item { {VALUES} }
  OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) = "en") }
  OPTIONAL { ?item schema:description ?description FILTER(LANG(?description) = "en") }
}
"""

DATES = """
SELECT ?item ?prop ?time ?precision WHERE { VALUES ?item { {VALUES} }
  { ?item p:P585 ?s . ?s psv:P585 ?v . BIND("P585" AS ?prop) }
  UNION { ?item p:P580 ?s . ?s psv:P580 ?v . BIND("P580" AS ?prop) }
  UNION { ?item p:P582 ?s . ?s psv:P582 ?v . BIND("P582" AS ?prop) }
  ?v wikibase:timeValue ?time ; wikibase:timePrecision ?precision .
}
"""

LOCATIONS = """
SELECT ?item ?kind ?location ?locationLabel ?coord ?iso ?continent ?area WHERE { VALUES ?item { {VALUES} }
  { ?item wdt:%s ?coord . BIND("own" AS ?kind) }
  UNION
  { { %s }
    ?location wdt:%s ?coord .
    OPTIONAL { ?location rdfs:label ?locationLabel FILTER(LANG(?locationLabel) = "en") }
    OPTIONAL { ?location wdt:P297 ?iso }
    OPTIONAL { ?location wdt:P31 wd:Q5107 . BIND(1 AS ?continent) }
    OPTIONAL { ?location wdt:P2046 ?area } }
}
""" % (OWN, ' UNION '.join(f'{{ ?item wdt:{p} ?location . BIND("{p}" AS ?kind) }}' for p in BORROWED), OWN)

# What kind of place each borrowed location is, and which countries it lies in.
LOCATION_TYPES = """
SELECT ?location ?type WHERE { VALUES ?location { {VALUES} }
  ?location wdt:P31 ?type .
}
"""

LOCATION_COUNTRIES = """
SELECT ?location ?country WHERE { VALUES ?location { {VALUES} }
  ?location wdt:P17 ?country .
}
"""


def write_rows(path, columns, rows, mode):
    new_file = mode == 'w' or not path.exists()
    with open(path, mode, newline='') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        if new_file:
            w.writerow(columns)
        for r in rows:
            w.writerow([r.get(c, '') for c in columns])


def fetch_missing(name, columns, template, ids):
    """Query `template` for the IDs not fetched before and append the results to data/raw/<name>."""
    done = F.fetched_ids(name)
    todo = sorted(set(ids) - done)
    if not todo:
        print(f'  {name:<28} up to date ({len(done):,})')
        return
    print(f'  {name:<28} fetching {len(todo):,} new')
    for start in range(0, len(todo), BATCH_SIZE):
        chunk = todo[start:start + BATCH_SIZE]
        rows = query(template.replace('{VALUES}', ' '.join('wd:' + q for q in chunk)))
        write_rows(C.RAW / name, columns, rows, 'a')
        with open(C.RAW / (name + '.done'), 'a') as fh:  # per batch, so an interrupted run resumes
            fh.write('\n'.join(chunk) + '\n')


def fetch_article_lengths(ev, ids):
    """Size in bytes of each event's English Wikipedia article, 50 titles per API request."""
    name = 'enwiki_lengths.tsv'
    todo = sorted(set(ids) - F.fetched_ids(name))
    if not todo:
        print(f'  {name:<28} up to date')
        return
    print(f'  {name:<28} fetching {len(todo):,} new')
    for start in range(0, len(todo), 50):
        chunk = todo[start:start + 50]
        lengths = wikipedia_lengths([ev[q]['enwiki'] for q in chunk])
        write_rows(C.RAW / name, ['item', 'bytes'],
                   [{'item': q, 'bytes': lengths.get(ev[q]['enwiki'], '')} for q in chunk], 'a')
        with open(C.RAW / (name + '.done'), 'a') as fh:
            fh.write('\n'.join(chunk) + '\n')


def wikipedia_lengths(titles):
    """{title as given: article length in bytes}, following redirects."""
    params = urllib.parse.urlencode({'action': 'query', 'prop': 'info', 'redirects': 1, 'format': 'json',
                                     'formatversion': 2, 'titles': '|'.join(titles)})
    req = urllib.request.Request(f'https://en.wikipedia.org/w/api.php?{params}', headers={
        'User-Agent': 'history-map/0.1 (https://github.com/ben-smith23/wikidata-map)'})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.load(r)['query']
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            wait = int(e.headers.get('Retry-After') or 10 * (attempt + 1))
            print(f'    rate limited, waiting {wait}s')
            time.sleep(wait)
    time.sleep(0.5)  # stay well under Wikipedia's rate limits
    # map each requested title through normalisation and redirects to the page it ends up at
    alias = {t: t for t in titles}
    for key in ('normalized', 'redirects'):
        step = {x['from']: x['to'] for x in res.get(key, [])}
        alias = {t: step.get(a, a) for t, a in alias.items()}
    length = {p['title']: p.get('length', '') for p in res['pages']}
    return {t: length.get(a, '') for t, a in alias.items()}


def column(name, col):
    return {r[col] for r in F.read(name) if r[col]}


def main():
    if '--refresh' in sys.argv and C.RAW.exists():
        shutil.rmtree(C.RAW)
    C.RAW.mkdir(parents=True, exist_ok=True)

    print('  candidates.tsv               fetching')
    write_rows(C.RAW / 'candidates.tsv', ['item', 'sitelinks', 'enwiki'], query(CANDIDATES), 'w')
    (C.RAW / 'FETCHED').write_text(datetime.date.today().isoformat() + '\n')

    ev = F.load_candidates()
    fetch_missing('types.tsv', ['item', 'type', 'typeLabel'], TYPES,
                  [q for q, e in ev.items() if e['langs'] >= C.LOWEST_MIN_LANGS])
    fetch_missing('type_ancestors.tsv', ['type', 'ancestor'], TYPE_ANCESTORS, column('types.tsv', 'type'))

    ev = F.load_candidates()  # now with types, so the early rules can run
    passing = [q for q, e in ev.items() if F.early_reason(q, e) is None]
    print(f'  {len(ev):,} candidates, {len(passing):,} pass the language and type rules')
    fetch_missing('labels.tsv', ['item', 'label', 'description'], LABELS, passing)
    fetch_missing('dates.tsv', ['item', 'prop', 'time', 'precision'], DATES, passing)
    fetch_article_lengths(ev, passing)
    fetch_missing('locations.tsv', ['item', 'kind', 'location', 'locationLabel', 'coord', 'iso', 'continent', 'area'],
                  LOCATIONS, passing)

    locations = column('locations.tsv', 'location')
    fetch_missing('location_types.tsv', ['location', 'type'], LOCATION_TYPES, locations)
    fetch_missing('location_countries.tsv', ['location', 'country'], LOCATION_COUNTRIES, locations)
    fetch_missing('location_type_ancestors.tsv', ['type', 'ancestor'], TYPE_ANCESTORS,
                  column('location_types.tsv', 'type'))


if __name__ == '__main__':
    main()

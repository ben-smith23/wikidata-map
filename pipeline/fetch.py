"""Step 1: download everything we might filter on from Wikidata (via QLever) into data/raw/.

Deliberately broad: every dated, located event with an English Wikipedia article, regardless of
language count or type. Filters are applied locally by filter_events.py, so changing them never
needs a re-fetch. Each file is skipped if it already exists; pass --refresh to re-download all.
"""
import csv
import datetime
import sys

from config import RAW
from sparql import query, query_batched

EVENTS = """
SELECT ?item (SAMPLE(?sl) AS ?sitelinks) (SAMPLE(?title) AS ?enwiki) WHERE {
  ?item wdt:P31/wdt:P279* wd:Q1190554 .
  ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> ; schema:name ?title .
  ?item wikibase:sitelinks ?sl .
  { ?item wdt:P585 ?d } UNION { ?item wdt:P580 ?d }
  { ?item wdt:P625 ?c } UNION { ?item wdt:P276 ?l . ?l wdt:P625 ?c }
} GROUP BY ?item
"""

LABELS = """
SELECT ?item ?label ?description WHERE { VALUES ?item { {VALUES} }
  OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) = "en") }
  OPTIONAL { ?item schema:description ?description FILTER(LANG(?description) = "en") }
}
"""

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
  { ?item wdt:P625 ?coord . BIND("own" AS ?kind) }
  UNION
  { ?item wdt:P276 ?location . ?location wdt:P625 ?coord . BIND("borrowed" AS ?kind)
    OPTIONAL { ?location rdfs:label ?locationLabel FILTER(LANG(?locationLabel) = "en") }
    OPTIONAL { ?location wdt:P297 ?iso }
    OPTIONAL { ?location wdt:P31 wd:Q5107 . BIND(1 AS ?continent) }
    OPTIONAL { ?location wdt:P2046 ?area } }
}
"""

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


def save(name, columns, rows):
    path = RAW / name
    tmp = path.with_suffix('.tmp')
    n = 0
    with open(tmp, 'w', newline='') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(columns)
        for r in rows:
            w.writerow([r.get(c, '') for c in columns])
            n += 1
    tmp.rename(path)
    print(f'  wrote {name}: {n:,} rows')


def read_column(name, column):
    with open(RAW / name) as fh:
        return sorted({r[column] for r in csv.DictReader(fh, delimiter='\t')})


def main():
    refresh = '--refresh' in sys.argv
    RAW.mkdir(parents=True, exist_ok=True)

    def step(name, columns, rows_fn):
        if (RAW / name).exists() and not refresh:
            print(f'  {name} exists, skipping')
            return
        print(f'  fetching {name}')
        save(name, columns, rows_fn())

    step('events.tsv', ['item', 'sitelinks', 'enwiki'], lambda: query(EVENTS))
    items = read_column('events.tsv', 'item')
    step('labels.tsv', ['item', 'label', 'description'], lambda: query_batched(LABELS, items))
    step('types.tsv', ['item', 'type', 'typeLabel'], lambda: query_batched(TYPES, items))
    types = read_column('types.tsv', 'type')
    step('type_ancestors.tsv', ['type', 'ancestor'], lambda: query_batched(TYPE_ANCESTORS, types))
    step('dates.tsv', ['item', 'prop', 'time', 'precision'], lambda: query_batched(DATES, items))
    step('locations.tsv', ['item', 'kind', 'location', 'locationLabel', 'coord', 'iso', 'continent', 'area'],
         lambda: query_batched(LOCATIONS, items))
    locations = [q for q in read_column('locations.tsv', 'location') if q]
    step('location_types.tsv', ['location', 'type'], lambda: query_batched(LOCATION_TYPES, locations))
    step('location_countries.tsv', ['location', 'country'], lambda: query_batched(LOCATION_COUNTRIES, locations))
    location_types = read_column('location_types.tsv', 'type')
    step('location_type_ancestors.tsv', ['type', 'ancestor'],
         lambda: query_batched(TYPE_ANCESTORS, location_types))

    (RAW / 'FETCHED').write_text(datetime.date.today().isoformat() + '\n')


if __name__ == '__main__':
    main()

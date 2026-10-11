"""Minimal client for the QLever Wikidata endpoint."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = 'https://qlever.dev/api/wikidata'
PREFIXES = """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX p: <http://www.wikidata.org/prop/>
PREFIX psv: <http://www.wikidata.org/prop/statement/value/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
"""
ENTITY = 'http://www.wikidata.org/entity/'
BATCH_SIZE = 3000


def _value(term):
    v = term['value']
    if term['type'] == 'uri' and v.startswith(ENTITY):
        return v[len(ENTITY):]
    return v


def query(sparql, retries=3):
    """Run a query and return a list of {variable: value} dicts. Entity URIs become bare QIDs."""
    data = urllib.parse.urlencode({'query': PREFIXES + sparql}).encode()
    req = urllib.request.Request(ENDPOINT, data=data, headers={
        'Accept': 'application/sparql-results+json',
        'User-Agent': 'history-map/0.1 (https://github.com/ben-smith23/wikidata-map)',
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                res = json.load(r)
            # QLever reports some failures as JSON without results instead of an HTTP error
            if 'results' not in res:
                raise RuntimeError(res.get('exception', res))
            return [{k: _value(t) for k, t in b.items()} for b in res['results']['bindings']]
        except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
            if attempt == retries - 1:
                raise
            print(f'    query failed ({e}), retrying...')
            time.sleep(10 * (attempt + 1))


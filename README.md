# History Map

A map of historical events from [Wikidata](https://www.wikidata.org): battles, disasters, treaties, revolutions, attacks and more. Every event has a date and a location.

## Layout

```
pipeline/
  config.py         every rule that decides what's on the map; edit this
  fetch.py          step 1: download candidates from Wikidata (via QLever) into data/raw/
  filter_events.py  step 2: apply the rules and write data/events.tsv
  build.py          step 3: write data/events.json, the file the map loads
  locations.py      turns coordinates into map points with a precision label
  sparql.py         small client for the QLever endpoint
data/               generated, not in git
  raw/              cached API results (~45 MB)
  events.tsv        the kept events, one per row; easy to inspect
  events.json       compact version for the map
```

## Running it

The pipeline is plain Python 3 with no dependencies. Run it from the repo root:

```sh
python3 pipeline/fetch.py          # incremental: only downloads events it hasn't seen before
python3 pipeline/filter_events.py  # seconds; prints what it removed and why
python3 pipeline/build.py
```

To change the rules, edit `pipeline/config.py` and re-run the last two steps; no API calls are needed. Running `fetch.py` again picks up new events; `--refresh` re-downloads everything, which is rarely needed.

## What counts as an event

Candidates are every Wikidata item that is an occurrence (Q1190554), has a date and a location (P625, P276, P131 or P17), and has an English Wikipedia article. An event is kept (about 29k) if:

- it has an article in **5+ Wikipedia languages**, which also serves as a measure of fame
- it's **dated to the year or better**, using whichever of "point in time" and "start time" is more precise, and it **isn't in the future**
- it **isn't sport, entertainment or an eclipse**, unless it's also a war, attack, disaster, political event or election. Sport with 40+ languages (Olympics, World Cups, but not league seasons) is kept.
- it **isn't a non-event** going by its Wikidata types: awards, trade fairs, holidays, eras, TV shows, sport delegations, currencies, bilateral relations, numbered parliamentary terms and so on

Elections and referendums are their own category (`election`), separate from `politics`.

Each event gets one or more points, all from a single source. That's its own coordinates (P625) if it has any. Otherwise it's whichever gives the more precise point: its "location" (P276) or its "located in the administrative territorial entity" (P131). Only if it has neither is its country (P17) used. Each point is labelled with how precise it is: `own`, `site`, `region`, `large_region`, `country` or `continent`.

## Credits

This started as a fork of [wmde/wikidata-map](https://github.com/wmde/wikidata-map) by Addshore, Michael, Tarrow and Ollieshotton, which maps the density of all Wikidata items. Data from Wikidata is CC0.

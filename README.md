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
python3 pipeline/fetch.py          # ~10 min the first time; skips files already in data/raw/
python3 pipeline/filter_events.py  # seconds; prints what it removed and why
python3 pipeline/build.py
```

To change the rules, edit `pipeline/config.py` and re-run the last two steps; no API calls are needed. To pick up new Wikidata edits, run `fetch.py --refresh`.

## What counts as an event

Candidates are every Wikidata item that is an occurrence (Q1190554), has a date and a location, and has an English Wikipedia article: about 119k. An event is kept (about 21k) if:

- it has an article in **5+ Wikipedia languages**, which also serves as a measure of fame
- it's **dated to the year or better**, using whichever of "point in time" and "start time" is more precise, and it **isn't in the future**
- it **isn't sport, entertainment or an eclipse**, unless it's also a war, attack, disaster or political event. Sport with 40+ languages (Olympics, World Cups, but not league seasons) is kept.
- it **isn't a non-event** going by its Wikidata types: awards, trade fairs, holidays, eras, TV shows and so on

Each event gets one or more points. These are its own coordinates, or failing that, those of its locations (P276). Each point is labelled with how precise it is: `own`, `site`, `region`, `large_region`, `country` or `continent`.

## Credits

This started as a fork of [wmde/wikidata-map](https://github.com/wmde/wikidata-map) by Addshore, Michael, Tarrow and Ollieshotton, which maps the density of all Wikidata items. Data from Wikidata is CC0.

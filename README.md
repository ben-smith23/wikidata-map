# Wikidata Map

A map of historical events from [Wikidata](https://www.wikidata.org): battles, disasters, treaties, revolutions, attacks and more. Every event has a date and a location.

## Layout

```
pipeline/
  config.py         every rule that decides what's on the map; edit this
  fetch.py          step 1: download candidates from Wikidata (via QLever) into data/raw/
  filter_events.py  step 2: apply the rules and write data/events.tsv
  build.py          step 3: write web/public/events.json, the file the map loads
  locations.py      turns coordinates into map points with a precision label
  sparql.py         small client for the QLever endpoint
data/               generated, not in git
  raw/              cached API results (~45 MB)
  events.tsv        the kept events, one per row; easy to inspect
web/                the map (Vite); web/public/events.json is committed so the site builds anywhere
```

## Running it

The pipeline is plain Python 3 with no dependencies. Run it from the repo root:

```sh
python3 pipeline/fetch.py          # incremental: only downloads events it hasn't seen before
python3 pipeline/filter_events.py  # seconds; prints what it removed and why
python3 pipeline/build.py
```

To change the rules, edit `pipeline/config.py` and re-run the last two steps; no API calls are needed. Running `fetch.py` again picks up new events; `--refresh` re-downloads everything, which is rarely needed.

The map is in `web/`: `npm install`, then `npm run dev` for a local server. Every push to `history-map` builds it and publishes it to GitHub Pages (`.github/workflows/pages.yml`).

## What counts as an event

Candidates are every Wikidata item that is an occurrence (Q1190554), has a date and a location (P625, P276, P131 or P17), and has an English Wikipedia article. An event is kept (about 20k) if:

- it has articles in **enough Wikipedia languages for its category**: 5 for war, attacks, disasters, politics and uncategorised; 12 for elections; 40 for sport. Entertainment and eclipses only stay if they're also in another category. An event uses the lowest cut among its categories.
- it **isn't a non-event**, judged by its Wikidata types and classes or its English Wikipedia title (the `NOT_EVENTS` table in `config.py`, with a `KEEP` list for exceptions): myths, hypothetical and cancelled events, sub-topics like "COVID-19 pandemic in Italy", awards, trade fairs, holidays, eras, sport delegations, currencies, league seasons, numbered parliamentary terms and so on
- it's **dated to the year or better**, using whichever of "point in time" and "start time" is more precise, and it **isn't in the future**
- it has a **usable location**
- it **isn't a low-profile event with a short article**. Events with 7 or fewer languages are dropped if their English article is in the bottom 40% by length among events of the same era and category. Comparing within an era keeps this from penalising older events, whose articles are shorter across the board.

Each event gets one or more points, all from a single source. That's its own coordinates (P625) if it has any. Otherwise it's whichever gives the more precise point: its "location" (P276) or its "located in the administrative territorial entity" (P131). Only if it has neither is its country (P17) used. Each point is labelled with how precise it is: `own`, `site`, `region`, `large_region`, `country` or `continent`.

## Credits

This started as a fork of [wmde/wikidata-map](https://github.com/wmde/wikidata-map) by Addshore, Michael, Tarrow and Ollieshotton, which maps the density of all Wikidata items. Data from Wikidata is CC0.

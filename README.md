# History Map

A map of historical events from [Wikidata](https://www.wikidata.org): battles, disasters, treaties, revolutions, attacks and more. Every event has a date and a location.

## Data pipeline

The pipeline is plain Python 3 with no dependencies. Run it from the repo root:

```sh
python3 pipeline/fetch.py          # 1. download from Wikidata via QLever (~10 min; cached in data/raw/)
python3 pipeline/filter_events.py  # 2. apply the rules in pipeline/config.py (seconds, local)
python3 pipeline/build.py          # 3. write data/events.json for the map
```

- **fetch** downloads every event in Wikidata that has a date, a location and an English Wikipedia article (about 119k). It skips files that already exist, so use `--refresh` to re-download.
- **filter** keeps the historically interesting ones (about 21k) and prints what it removed and why. All the rules live in `pipeline/config.py`.
- **build** writes the compact JSON that the map loads.

### Current rules

- The event has an article in 5+ Wikipedia languages. The language count also serves as a measure of fame.
- It is dated to at least the year, using whichever of "point in time" and "start time" is more precise. No future events.
- Sport, awards, festivals, pageants and eclipses are dropped unless the event is also a war, attack, disaster or political event. Sport with 40+ languages is kept, e.g. the Olympics and World Cups.
- Location is the event's own coordinate if it has one; otherwise it is borrowed from its location (P276). Each point records how precise it is: own, site, region, large region, country or continent.

## Credits

This started as a fork of [wmde/wikidata-map](https://github.com/wmde/wikidata-map) by Addshore, Michael, Tarrow and Ollieshotton, which maps the density of all Wikidata items.

"""Every filtering rule lives here. Change a value, re-run filter_events.py; no API calls needed."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'          # API results, cached by fetch.py
EVENTS_TSV = ROOT / 'data' / 'events.tsv'    # output of filter_events.py
EVENTS_JSON = ROOT / 'data' / 'events.json'  # output of build.py (what the map loads)

# --- Which events -----------------------------------------------------------
# Number of Wikipedia language editions with an article about the event.
MIN_LANGS = 5

# Coarsest date we accept. Wikidata precision: 11=day, 10=month, 9=year, 8=decade, 7=century.
MIN_DATE_PRECISION = 9

# Sport is dropped unless it has at least this many languages (Olympics, World Cups).
SPORT_MIN_LANGS = 40

# Specific items that slip through every rule.
BLOCKLIST = {
    'Q4115189',  # Wikidata Sandbox (test item)
}

# --- Categories ---------------------------------------------------------------
# An event belongs to a category if any of its types is a subclass of one of these.
CATEGORIES = {
    'war': ['Q178561', 'Q198', 'Q350604', 'Q180684', 'Q645883', 'Q188055'],
    # battle, war, armed conflict, conflict, military operation, siege
    'attack': ['Q2223653', 'Q3199915', 'Q132821', 'Q750215'],
    # terrorist attack, massacre, murder, mass murder
    'disaster': ['Q3839081', 'Q171558', 'Q8065', 'Q3241045'],
    # disaster, accident, natural disaster, disease outbreak
    'politics': ['Q131569', 'Q124734', 'Q45382', 'Q273120', 'Q40231', 'Q625994', 'Q29102902'],
    # treaty, rebellion, coup, protest, election, convention, papal election
    'sport': ['Q16510064', 'Q27020041', 'Q13406554', 'Q500834'],
    # sporting event, sports season, sports competition, tournament
    'entertainment': ['Q4504495', 'Q58863414', 'Q1573906', 'Q182832', 'Q132241'],
    # award ceremony, beauty pageant, concert tour, concert, festival
    'eclipse': ['Q3887', 'Q141022'],
    # solar eclipse, eclipse
}

# Events in these categories always stay, even if they are also in a dropped category.
HISTORICAL = {'war', 'attack', 'disaster', 'politics'}

# Dropped unless the event is also HISTORICAL (sport has the SPORT_MIN_LANGS exception).
DROPPED = {'sport', 'entertainment', 'eclipse'}

# Types Wikidata doesn't file under the roots above, matched on their English label.
JUNK_TYPE_LABELS = re.compile(r'\bdraft\b|\bcensus\b|^road$|^water transport$', re.I)
ENTERTAINMENT_TYPE_LABELS = re.compile(
    r'festival|pageant|eurovision|archery championships|olympic games (opening|closing) ceremony', re.I)

# --- Locations ----------------------------------------------------------------
# When an event has no coordinate of its own we borrow its location's, and record how vague that is:
#   site < region < large_region < country < continent
# Rules are checked in this order; the first match wins (see location_kind in filter_events.py):
#   1. continent                    -> continent
#   2. has an ISO country code      -> country (or site, if smaller than REGION_MIN_AREA, e.g. Monaco)
#   3. LOCATION_CLASSES['country']  -> country
#   4. LOCATION_CLASSES['site']     -> site (cities stay precise however large their area)
#   5. has an area                  -> site / region / large_region by the thresholds below
#   6. LOCATION_CLASSES['large_region'] -> large_region
#   7. LOCATION_CLASSES['region']   -> region, or large_region if it spans 0 or 3+ countries
#   8. anything else                -> site (buildings, stadiums, battlefields, lakes...)
REGION_MIN_AREA = 1_000
LARGE_REGION_MIN_AREA = 50_000
REGION_MAX_COUNTRIES = 2

LOCATION_CLASSES = {
    'country': ['Q3024240'],
    # historical country
    'site': ['Q486972', 'Q811979'],
    # human settlement, architectural structure
    'large_region': ['Q9430', 'Q165', 'Q3502482', 'Q182547', 'Q28171280'],
    # ocean, sea, cultural region, Roman province, ancient civilization
    'region': ['Q82794', 'Q1620908', 'Q4022', 'Q37901', 'Q39594', 'Q46831', 'Q34763', 'Q133346'],
    # geographic region, historical region, river, strait, bay, mountain range, peninsula, border
}

"""Every rule that decides which events are on the map. Edit, then re-run filter_events.py (no API calls)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'                  # fetch.py writes here
EVENTS_TSV = ROOT / 'data' / 'events.tsv'    # filter_events.py writes the kept events here
EVENTS_JSON = ROOT / 'data' / 'events.json'  # build.py writes the file the map loads here

# --- Fame -----------------------------------------------------------------------
# Number of Wikipedia language editions with an article about the event.
MIN_LANGS = 5

# --- Dates ------------------------------------------------------------------------
# Coarsest date we accept. Wikidata precision: 11=day, 10=month, 9=year, 8=decade, 7=century.
MIN_DATE_PRECISION = 9

# --- Categories ---------------------------------------------------------------------
# An event is in a category if any of its types is a subclass of one of these Wikidata classes.
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

# Events in a HISTORICAL category are never dropped by the category or type-name rules below.
HISTORICAL = {'war', 'attack', 'disaster', 'politics'}
DROPPED_CATEGORIES = {'sport', 'entertainment', 'eclipse'}

# Exception: sport with this many languages stays (Olympics, World Cups)...
SPORT_MIN_LANGS = 40
# ...except league seasons. Wikidata types them like World Cups, so match the name instead.
SEASON_LABEL = re.compile(r'^\d{4}[–-]\d{2,4} ')  # "2017–18 Premier League"

# --- Type-name rules ------------------------------------------------------------------
# For non-events Wikidata doesn't file under the categories above, matched on English type labels.

# Never a real event, so dropped even if HISTORICAL: the Trojan War is typed "mythical war", and fan
# conventions count as politics because Wikidata files them under "convention".
DROP_ALWAYS_IF_ANY_TYPE = re.compile(
    r'myth|hypothetical|title of mary|fan convention|anime convention|gaming convention', re.I)

# Strong signal: dropped if ANY of the event's types matches.
DROP_IF_ANY_TYPE = re.compile('|'.join([
    r'\bdraft\b|\bcensus\b|^road$|^water transport$',            # NBA draft, census, mislabelled roads
    r'festival|pageant|eurovision|archery championships',        # film festivals, Miss Universe
    r'olympic games (opening|closing) ceremony',
]), re.I)

# Weak signal: dropped only if EVERY type matches this (or is GENERIC), so real events that also
# carry an odd type survive, e.g. a pope's funeral that Wikidata also calls a "public holiday".
DROP_IF_ONLY_TYPES = re.compile('|'.join([
    r'holiday|commemoration|anniversary|observance|\bpride\b|festivity|carnival|mardi gras|world day',  # April Fools' Day
    r'\bawards?\b|\bprize\b|lecture series|^lecture',                       # Golden Lion, MTV EMAs
    r'trade fair|fashion week|auto show|computer expo|toy fair|motor show|video game|cosplay|^expo$',  # CeBIT
    r'delegation|nation at the',                                            # "Greece at the 2000 Olympics"
    r'television|\btv\b|web series|news|radio|newspaper|^university$|^organization$|media outlet',
    r'song contest|national final|reality|interview|film$',                 # Bundesvision, Survivor
    r'music competition|franchise',                                         # Eurovision (the series), Chopin Competition
    r'currency|^mark$',                                                     # Deutsche Mark
    r'art movement|art style|art group|literary movement|cultural movement|golden age|^era$|periodization',
    r'archaeological culture',                                              # Amratian culture
    # (art exhibitions are deliberately not here: Salon des Refusés, Armory Show, Degenerate Art)
    r'^historical period$|decade|^style',                                   # Roaring Twenties
    r'gospel episode|narrative event|pericope|legend|myth|anecdote|paranormal|artistic theme|resurrection',
    r'apparition|miracle',                                                  # Lourdes apparitions
]), re.I)
GENERIC_TYPES = re.compile(
    r'^(recurring event|recurring event edition|occurrence|event|planned event|annual event|historical event|Q\d+)$',
    re.I)

# Specific items that slip through every rule.
BLOCKLIST = {
    'Q4115189',  # Wikidata Sandbox (test item)
    'Q1129327',  # Music Day: a holiday typed only as "party", which would also catch real celebrations
    'Q582706',   # Israeli settlement: a general concept, not an event
    'Q668984',   # Google I/O: tech conference, counts as politics via "convention"
    'Q884557',   # BlizzCon: same
    'Q3617564',  # Animefest: anime convention typed only as convention + festival
}

# --- Locations ------------------------------------------------------------------------
# An event's points come from ONE source: its own coordinate (P625) if it has one, otherwise
# whichever of these properties gives the most precise point (ties go to the one listed first).
LOCATION_SOURCES = ['P276', 'P131']  # location, located in the administrative territorial entity
# Last resort, used only when an event has none of the above. None to leave such events out.
LOCATION_FALLBACK = None  # 'P17' (country)

# Borrowed points record how vague they are: site < region < large_region < country < continent.
# See locations.location_kind for the order the rules are checked in.
REGION_MIN_AREA = 1_000        # km²; smaller than this is a site
LARGE_REGION_MIN_AREA = 50_000
REGION_MAX_COUNTRIES = 2       # a region spanning 0 or more countries than this is a large region

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

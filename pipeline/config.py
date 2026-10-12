"""Every rule that decides which events are on the map. Edit, then re-run filter_events.py (no API calls)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'                  # fetch.py writes here
EVENTS_TSV = ROOT / 'data' / 'events.tsv'    # filter_events.py writes the kept events here
EVENTS_JSON = ROOT / 'web' / 'public' / 'events.json'  # the file the map loads; committed, so the site can be built anywhere

# --- Fame ---------------------------------------------------------------------------
# Minimum number of Wikipedia language editions with an article, per category. An event uses the
# LOWEST cut among its categories, so a battle that is also a sporting event needs only the war cut.
# None means the category on its own never qualifies (an event needs another category to stay).
MIN_LANGS = {
    'war': 5, 'attack': 5, 'disaster': 5, 'politics': 5,
    'election': 12,            # below 12, election articles are mostly stubs or results tables
    'uncategorised': 5,        # events in none of the CATEGORIES below
    'sport': 40,               # Olympics, World Cups
    'entertainment': None,
    'eclipse': None,
}
LOWEST_MIN_LANGS = min(v for v in MIN_LANGS.values() if v is not None)  # fetch.py downloads from here up

# Trim: events with at most TRIM_MAX_LANGS languages are dropped if their English Wikipedia article is
# in the bottom TRIM_PERCENTILE% by length among events of the same era and category. Comparing within
# an era matters: articles about recent events are 3-4x longer across the board, so a plain length
# cut would mostly remove older history.
TRIM_MAX_LANGS = 7
TRIM_PERCENTILE = 40
ERAS = [1500, 1800, 1900, 1950, 2000, 2015]  # boundaries: before 1500, 1500-1799, ..., 2015 on

# --- Dates ----------------------------------------------------------------------------
# Coarsest date we accept. Wikidata precision: 11=day, 10=month, 9=year, 8=decade, 7=century.
MIN_DATE_PRECISION = 9
# Earliest year kept (negative = BC).
EARLIEST_YEAR = -1500

# --- Categories -----------------------------------------------------------------------
# An event is in a category if any of its types is a subclass of one of these Wikidata classes.
CATEGORIES = {
    'war': ['Q178561', 'Q198', 'Q350604', 'Q180684', 'Q645883', 'Q188055'],
    # battle, war, armed conflict, conflict, military operation, siege
    'attack': ['Q2223653', 'Q3199915', 'Q132821', 'Q750215'],
    # terrorist attack, massacre, murder, mass murder
    'disaster': ['Q3839081', 'Q171558', 'Q8065', 'Q3241045'],
    # disaster, accident, natural disaster, disease outbreak
    'politics': ['Q131569', 'Q124734', 'Q45382', 'Q273120', 'Q625994'],
    # treaty, rebellion, coup, protest, convention
    'election': ['Q40231', 'Q43109', 'Q29102902'],
    # election, referendum, papal election
    'sport': ['Q16510064', 'Q27020041', 'Q13406554', 'Q500834'],
    # sporting event, sports season, sports competition, tournament
    'entertainment': ['Q4504495', 'Q58863414', 'Q1573906', 'Q182832', 'Q132241'],
    # award ceremony, beauty pageant, concert tour, concert, festival
    'eclipse': ['Q3887', 'Q141022'],
    # solar eclipse, eclipse
}

# --- Not events -----------------------------------------------------------------------
# Things Wikidata calls occurrences that aren't events. A rule matches when ALL its conditions hold:
#   types     regex on the English labels of the event's types; any one type matching is enough,
#             unless every=True: then every type must match (ignoring GENERIC_TYPES). That's for weak
#             signals, so e.g. a pope's funeral that is also typed "public holiday" survives.
#   title     regex on the English Wikipedia title
#   classes   Wikidata classes: a type matches if it is one of these or a subclass. A type matches a
#             rule if its label matches `types` OR it falls under `classes`; classes catch variants
#             named differently, labels cover noise that has no clean class.
#   items     specific QIDs
#   category  the event must be in this category
# Rules don't apply to events in a HISTORICAL category unless even_if_historical=True.
# Rules are checked in order; the first match is reported as the reason.
HISTORICAL = {'war', 'attack', 'disaster', 'politics', 'election'}
GENERIC_TYPES = r'^(recurring event|recurring event edition|occurrence|event|planned event|annual event|historical event|Q\d+)$'

# Exceptions: real events that a NOT_EVENTS rule would otherwise catch. They still need enough
# languages, a date and a location.
KEEP = {
    'Q3704511',  # Decimal Day (UK switch to decimal currency, 1971), caught by the currency class
}

NOT_EVENTS = [
    dict(reason='blocklist', even_if_historical=True, items={
        'Q4115189',  # Wikidata Sandbox (test item)
        'Q1129327',  # Music Day: a holiday typed only as "party", which would also catch real celebrations
        'Q582706',   # Israeli settlement: a general concept, not an event
        'Q668984',   # Google I/O: tech conference, counts as politics via "convention"
        'Q884557',   # BlizzCon: same
        'Q3617564',  # Animefest: anime convention typed only as convention + festival
        'Q758861',   # USSR State Prize: an award, typed as a prize plus "title of honor"
    }),
    dict(reason='not real: myth, hypothetical, cancelled, Marian title, fan convention', even_if_historical=True,
         types=r'myth|hypothetical|cancel(?!led election)|title of mary|fan convention|anime convention|gaming convention',
         classes={'Q12827256', 'Q24336068', 'Q390248',               # myth, mythical war, myth of origins
                  'Q55118684', 'Q114350932', 'Q87479384',            # cancelled: sports event, military op, due to COVID
                  'Q1509831', 'Q1129398', 'Q548126'}),               # title of Mary, fan convention, anime convention
         # (not the broad "cancelled event" class: "cancelled election" sits under it)
         # Trojan War ("mythical war"), 1944 Winter Olympics (cancelled; but annulled elections did happen); fan conventions count as
         # politics via "convention"
    dict(reason='sub-topic or aggregate, not an event', even_if_historical=True, title='|'.join([
        r'^(\d{4}(–\d{2,4})? )?COVID-19 pandemic (in|on) ',  # "COVID-19 pandemic in Oregon"
        r'^history of ',                                   # "history of Melbourne"
        r'^list of ',                                      # "List of wars involving Saudi Arabia"
        r'^(premiership|presidency|chancellorship) of ',   # "premiership of Boris Johnson"
        r' (cyclone|hurricane|typhoon|tornado) season$',   # "2019–20 Australian region cyclone season"
    ])),
    dict(reason='type: draft, census, festival, delegation, currency...', types='|'.join([
        r'\bdraft\b|\bcensus\b|^road$|^water transport$',            # NBA draft, census, mislabelled roads
        r'festival|pageant|eurovision|archery championships',        # film festivals, Miss Universe
        r'olympic games (opening|closing) ceremony',
        r'delegation|nation at|paralympics team|olympic team',       # "Jamaica at the 2020 Summer Olympics"
        r'bilateral relation|history of a country',                  # "Russia–Ukraine relations"
        r'currency|coin type|banknote',                              # US dollar, French franc, £10 note
        r'anthem|magazine|streaming|train service|same-sex marriage|presidential campaign',
        r'movement in cinema|painting movement',                     # French New Wave
    ]), classes={
        'Q31603', 'Q39825', 'Q4350743', 'Q2658935',                 # draft, census (x2), beauty contest
        'Q27787439', 'Q41582469', 'Q868557', 'Q4801521',            # film/music festival editions, music/arts festival
        'Q54802199', 'Q110288240', 'Q2231681',                      # Eurovision entries & editions, World Archery Ch.
        'Q130192067', 'Q94998068',                                  # Olympic opening/closing ceremony
        'Q26213387', 'Q46195901', 'Q26760286', 'Q35823051',         # Olympic/Paralympic delegations, World Athletics entries
        'Q17544377', 'Q8142', 'Q47433', 'Q23691',                   # history of a country, currency, banknote, anthem
        'Q847906', 'Q63241860', 'Q17422',                           # online magazine, streaming service, same-sex marriage
        'Q3001152', 'Q3326867', 'Q155930',                          # cinema/painting movement, water transport
    }),
    dict(reason='league season, group stage or Olympic bid', category='sport', title='|'.join([
        r'^\d{4}[–-]\d{2,4} ',   # "2017–18 Premier League": Wikidata types these like World Cups
        r' Group [A-H]$',        # "2018 FIFA World Cup Group A"
        r'^bids? for ',          # "Bids for the 2012 Summer Olympics"
    ])),
    dict(reason='numbered parliamentary term', types=r'^legislative term$', classes={'Q15238777'},
         title=r'^\d+(st|nd|rd|th) '),
         # "117th United States Congress"; one-off assemblies (Estates General of 1789) are typed the same
    dict(reason='not an event: award, trade fair, holiday, era...', every=True, types='|'.join([
        r'holiday|commemoration|anniversary|observance|\bpride\b|festivity|carnival|mardi gras|world day',
        r'\bawards?\b|\bprize\b|lecture series|^lecture',                   # Golden Lion, MTV EMAs
        r'trade fair|fashion week|auto show|computer expo|toy fair|motor show|video game|cosplay|^expo$',
        r'television|\btv\b|web series|news|radio|newspaper|^university$|^organization$|media outlet',
        r'song contest|national final|reality|interview|film$',             # Bundesvision, Survivor
        r'music competition|franchise',                                     # Eurovision (the series)
        r'^mark$',                                                          # Deutsche Mark
        r'art movement|art style|art group|literary movement|cultural movement|golden age|^era$|periodization',
        r'archaeological culture',                                          # Amratian culture
        r'^historical period$|decade|^style',                               # Roaring Twenties
        r'gospel episode|narrative event|pericope|legend|myth|anecdote|paranormal|artistic theme|resurrection',
        r'apparition|miracle',                                              # Lourdes apparitions
        # (art exhibitions are deliberately not here: Salon des Refusés, Armory Show, Degenerate Art)
    ]), classes={
        'Q4504495', 'Q2558684', 'Q51404', 'Q4618',                  # award ceremony, world day, Pride parade, Carnival
        'Q253946', 'Q1156329', 'Q2613738',                          # fashion week, auto show, computer expo
        'Q15416', 'Q526877', 'Q11032', 'Q178651', 'Q20603222',      # TV programme, web series, newspaper, interview, classical music competition
        'Q4281830', 'Q3326717', 'Q465299',                          # mark (currency), literary movement, archaeological culture
        'Q106355253', 'Q507850', 'Q950249', 'Q26913948',            # gospel episode, Marian apparition, Eucharistic miracle, legendary battle
    }),
]

# A year in the English Wikipedia title wins over a date it disagrees with ("2013 Cypriot presidential
# election" dated 2008). Only a leading year or decade, a bracketed year or range, or a trailing "of 1770"
# count, so flight numbers don't. Titles matching this are skipped: they name a later event.
TITLE_YEAR_EXCEPTIONS = r'qualification|\bbid\b'

# Events that span more than this many years and have no category are eras, legal codes, awards and the
# like (the Roman calendar, the Great Qing Legal Code, Sakoku), not events.
MAX_UNCATEGORISED_SPAN = 100

# --- Corrections -----------------------------------------------------------------------
# Errors in Wikidata found by auditing the list: own coordinates far from the places an event names, years
# in titles that disagree with the date. Each entry replaces the event's point, start or end; a date is
# (ISO date, precision: 11 day, 10 month, 9 year). drop=True removes an event whose fix isn't certain.
CORRECTIONS = {
    # wrong coordinates (sign flips, typos, a namesake place)
    'Q126876': dict(point=(-73.41667, 43.66667)),            # Saratoga campaign: longitude sign flipped (was Kazakhstan)
    'Q3555607': dict(point=(48.5158, 34.7961)),              # Battle of Ecbatana: latitude typo (was the Indian Ocean)
    'Q20820893': dict(point=(48.85, 38.75)),                 # Siege of Lankaran: was central Russia
    'Q2124166': dict(point=(46.7167, 43.85)),                # 2010 Kizlyar bombings: latitude typo
    'Q12756567': dict(point=(20.45, 44.82)),                 # Siege of Belgrade (1440): was Italy
    'Q2888872': dict(point=(112.19, 30.35)),                 # Battle of Jiangling (208): was Jiangsu
    'Q2386936': dict(point=(-76.89, 18.37)),                 # Tacky's Revolt: Jamaica, was French Guiana
    'Q5432166': dict(point=(35.84, 34.44)),                  # Fall of Tripoli (1289): Lebanon, not Libya
    'Q1308854': dict(point=(-99.13, 19.43)),                 # La Noche Triste: Tenochtitlan, was Sonora
    'Q109837841': dict(point=(-83.26, 42.84)),               # 2021 Oxford High School shooting: Michigan, was Colorado
    'Q12857637': dict(point=(4.38, 50.84)),                  # 40th G7 summit: held in Brussels, not Sochi
    'Q615020': dict(point=(8.52, 12.0)),                     # EAS Airlines Flight 4226: crashed in Kano, not Lagos
    'Q24262455': dict(point=(12.24, 51.83)),                 # Murder of Yangjie Li: Dessau, was Iowa City
    'Q961673': dict(point=(2.12, 48.80)),                    # Treaty of Versailles (1768): was Versailles, Kentucky
    'Q2602266': dict(point=(-0.235, 51.35)),                 # Treaty of Nonsuch: Nonsuch Palace, was Florida
    'Q2422375': dict(point=(-4.0, 40.0), kind='large_region'),  # Roman conquest of the Iberian Peninsula: was Italy
    'Q3636516': dict(point=(42.54, 39.14)),                  # Siege of Manzikert (1054): Malazgirt, was central Anatolia
    'Q593024': dict(point=(5.41, 36.19)),                    # Sétif and Guelma massacre: Sétif, was the Sahara
    # wrong dates
    'Q1633080': dict(end=('2007-12-15', 11)),                # 2007 UN Climate Change Conference: end was 2017
    'Q856650': dict(date=('1990-08-02', 11)),                # Iraqi invasion of Kuwait: was 2009
    'Q714820': dict(date=('1877-01-29', 11)),                # Satsuma Rebellion: was 2005
    'Q111123805': dict(date=('2022-03-05', 11), point=(-100.446, 20.577)),  # Querétaro–Atlas riot: was 40 AD in Barcelona
    'Q68750': dict(date=('1810-09-16', 11), point=(-102.0, 23.0), kind='country'),  # Mexican War of Independence: was 1800 in Canada
    # wrong, and the right place isn't certain
    'Q1355254': dict(drop=True),                             # Battle of Poimanenon: placed in Syria
    'Q4871427': dict(drop=True),                             # Battle of Khresili: in Georgia, placed in Ukraine
}

# --- Locations ------------------------------------------------------------------------
# An event's points come from ONE source: its own coordinate (P625) if it has one, otherwise
# whichever of these properties gives the most precise point (ties go to the one listed first).
LOCATION_SOURCES = ['P276', 'P131']  # location, located in the administrative territorial entity
# Last resort, used only when an event has none of the above. None to leave such events out.
LOCATION_FALLBACK = 'P17'  # country; set to None to leave country-only events out

# Borrowed points record how vague they are: site < region < large_region < country < continent.
# See locations.location_kind for the order the rules are checked in.
REGION_MIN_AREA = 1_000        # km²; smaller than this is a site
LARGE_REGION_MIN_AREA = 50_000
REGION_MAX_COUNTRIES = 2       # a region spanning 0 or more countries than this is a large region

# Locations that are never used: a vehicle's coordinates are where it is now (a museum ship, a wreck),
# not where the event happened, e.g. the USS Iowa turret explosion would be placed in Los Angeles.
IGNORED_LOCATION_CLASSES = {'Q42889'}  # vehicle


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

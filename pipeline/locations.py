"""Turning an event's coordinates (or its locations' coordinates) into map points with a precision label."""
import math
import re

import config as C

POINT = re.compile(r'^POINT\((\S+) (\S+)\)$')  # Earth only; other globes are prefixed with a URI
KINDS = ['own', 'site', 'region', 'large_region', 'country', 'continent']  # most to least precise
LOCATION_CLASSES = {kind: set(qids) for kind, qids in C.LOCATION_CLASSES.items()}


def location_kind(loc):
    """How vague a borrowed location is. The first matching rule wins."""
    is_a = lambda kind: bool(loc['classes'] & LOCATION_CLASSES[kind])
    if loc['continent']:
        return 'continent'
    if loc['iso']:  # has a country code; tiny countries like Monaco are as precise as a city
        return 'site' if 0 < loc['area'] < C.REGION_MIN_AREA else 'country'
    if is_a('country'):
        return 'country'
    if is_a('site'):  # cities stay precise however large their area
        return 'site'
    if loc['area']:
        if loc['area'] > C.LARGE_REGION_MIN_AREA:
            return 'large_region'
        return 'region' if loc['area'] > C.REGION_MIN_AREA else 'site'
    if is_a('large_region'):
        return 'large_region'
    if is_a('region'):
        return 'region' if 1 <= loc['countries'] <= C.REGION_MAX_COUNTRIES else 'large_region'
    return 'site'  # buildings, stadiums, battlefields, lakes...


def parse_point(coord):
    m = POINT.match(coord)
    if not m:
        return None
    lon, lat = float(m.group(1)), float(m.group(2))
    return (round(lon, 5), round(lat, 5)) if -180 <= lon <= 180 and -90 <= lat <= 90 else None


def _borrowed_points(locations):
    pts = {}
    for loc in locations.values():
        if loc['classes'] & C.IGNORED_LOCATION_CLASSES:
            continue
        kind = location_kind(loc)
        for p in filter(None, map(parse_point, loc['coords'])):
            # if two locations share a point, keep the more precise kind
            if p not in pts or KINDS.index(kind) < KINDS.index(pts[p]):
                pts[p] = kind
    return pts


def best_kind(pts):
    return min(pts.values(), key=KINDS.index)


def points_for(own_coords, borrowed):
    """Returns (source, {(lon, lat): kind}). `borrowed` maps a property (P276, P131) to its locations.

    Uses the event's own coordinates if it has usable ones, otherwise the LOCATION_SOURCES property
    whose most precise point beats the others'. Sources are never mixed, so an event with P276 = Paris
    and P131 = Île-de-France gets just Paris."""
    pts = {p: 'own' for p in map(parse_point, own_coords) if p}
    if pts:
        return 'P625', pts
    source, best = None, {}
    for prop in C.LOCATION_SOURCES:
        candidate = _borrowed_points(borrowed.get(prop, {}))
        if candidate and (not best or KINDS.index(best_kind(candidate)) < KINDS.index(best_kind(best))):
            source, best = prop, candidate
    if not best and C.LOCATION_FALLBACK:
        fallback = _borrowed_points(borrowed.get(C.LOCATION_FALLBACK, {}))
        if fallback:
            source, best = C.LOCATION_FALLBACK, fallback
    return source, best


def spread_km(points):
    """Largest distance between any two points."""
    def haversine(a, b):
        lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
        h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        return 2 * 6371 * math.asin(math.sqrt(min(1, h)))
    return round(max((haversine(a, b) for i, a in enumerate(points) for b in points[i + 1:]), default=0))

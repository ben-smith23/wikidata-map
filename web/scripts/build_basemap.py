"""Build the static basemap files in web/public/basemap/ from Natural Earth (public domain).

Downloads sources once into data/basemap_src/ (gitignored), then writes compact files:
  rivers.json, lakes.json,  GeoJSON with only a rank property, coordinates rounded
  states.json               (states.json: state/province borders for large federal countries)
  labels.json               [{name, kind, lon, lat, rank}] for oceans/seas, physical regions,
                            countries and cities
  relief.webp               shaded relief reprojected to Equal Earth (same maths as d3.geoEqualEarth)

Run from the repo root: python3 web/scripts/build_basemap.py
"""
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'data' / 'basemap_src'
OUT = ROOT / 'web' / 'public' / 'basemap'
GEOJSON = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson'
RELIEF = 'https://naciscdn.org/naturalearth/50m/raster/SR_50M.zip'
RELIEF_WIDTH = 8192
# Physical regions worth a label: big landforms, not capes, islands or coasts.
REGION_CLASSES = {'Range/mtn', 'Desert', 'Plateau', 'Basin', 'Plain', 'Tundra', 'Lowland', 'Delta'}  # output pixels; the world is ~2:1 in Equal Earth


def download(url, name):
    path = SRC / name
    if not path.exists():
        print('downloading', name)
        urllib.request.urlretrieve(url, path)
    return path


def geojson(name):
    return json.loads(download(GEOJSON.format(name), name + '.geojson').read_text())


def rounded(coords):
    if coords and isinstance(coords[0], (int, float)):
        return [round(coords[0], 3), round(coords[1], 3)]
    return [rounded(c) for c in coords if c]  # some sources contain empty rings


def slim(fc, rank_key):
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'rank': f['properties'].get(rank_key) or 0},
         'geometry': {'type': f['geometry']['type'], 'coordinates': rounded(f['geometry']['coordinates'])}}
        for f in fc['features'] if f['geometry']]}


def label_point(geometry):
    """A point well inside the largest polygon (a rough pole of inaccessibility), for sea names."""
    polys = geometry['coordinates'] if geometry['type'] == 'MultiPolygon' else [geometry['coordinates']]
    ring = np.array(max((p[0] for p in polys), key=len))
    (x0, y0), (x1, y1) = ring.min(0), ring.max(0)
    xs, ys = np.meshgrid(np.linspace(x0, x1, 60), np.linspace(y0, y1, 60))
    pts = np.c_[xs.ravel(), ys.ravel()]
    # even-odd point-in-polygon test against the outer ring
    inside = np.zeros(len(pts), bool)
    a, b = ring, np.roll(ring, -1, axis=0)
    for (ax, ay), (bx, by) in zip(a, b):
        crosses = ((ay > pts[:, 1]) != (by > pts[:, 1])) & \
                  (pts[:, 0] < (bx - ax) * (pts[:, 1] - ay) / (by - ay + 1e-12) + ax)
        inside ^= crosses
    if not inside.any():
        return ring.mean(0).tolist()
    cand = pts[inside]
    dist = np.min(np.linalg.norm(cand[:, None, :] - ring[None, ::max(1, len(ring) // 400), :], axis=2), axis=1)
    return cand[dist.argmax()].tolist()


def labels():
    out = []
    for f in geojson('ne_50m_geography_marine_polys')['features']:
        p = f['properties']
        kind = 'ocean' if p['featurecla'] == 'ocean' else 'sea'
        lon, lat = label_point(f['geometry'])
        name = p['name'] or p['name_en']  # 'name' keeps North/South Atlantic apart; name_en merges them
        name = name.title() if name.isupper() else name
        out.append(dict(name=name, kind=kind, lon=round(lon, 3), lat=round(lat, 3), rank=p['scalerank']))
    seen = set()
    for f in geojson('ne_50m_geography_regions_polys')['features']:
        p = f['properties']
        if p['FEATURECLA'] not in REGION_CLASSES or not f['geometry'] or p['NAME'] in seen:
            continue  # one label per name: some regions are split into several polygons
        seen.add(p['NAME'])
        lon, lat = label_point(f['geometry'])
        out.append(dict(name=(p['NAME_EN'] or p['NAME']).title(), kind='region', lon=round(lon, 3), lat=round(lat, 3),
                        rank=p['SCALERANK']))
    for f in geojson('ne_110m_admin_0_countries')['features']:
        p = f['properties']
        out.append(dict(name=p['NAME_EN'] or p['NAME'], kind='country', lon=round(p['LABEL_X'], 3), lat=round(p['LABEL_Y'], 3),
                        rank=p['LABELRANK']))
    for f in geojson('ne_50m_populated_places_simple')['features']:
        p = f['properties']
        out.append(dict(name=p['name'], kind='city', lon=round(p['longitude'], 3), lat=round(p['latitude'], 3), rank=p['scalerank']))
    return out


# --- Equal Earth (Šavrič, Patterson & Jenny 2018), identical to d3.geoEqualEarthRaw ----------------
A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = np.sqrt(3) / 2


def equal_earth_y(theta):
    t2 = theta * theta
    return theta * (A1 + A2 * t2 + t2 ** 3 * (A3 + A4 * t2))


def equal_earth_invert(x, y):
    """Projected (x, y) -> (lon, lat) in radians; NaN outside the globe."""
    theta = y.copy()
    for _ in range(12):  # Newton's method on y(theta)
        t2 = theta * theta
        dy = A1 + 3 * A2 * t2 + t2 ** 3 * (7 * A3 + 9 * A4 * t2)
        theta -= (equal_earth_y(theta) - y) / dy
    t2 = theta * theta
    lon = M * x * (A1 + 3 * A2 * t2 + t2 ** 3 * (7 * A3 + 9 * A4 * t2)) / np.cos(theta)
    lat = np.arcsin(np.clip(np.sin(theta) / M, -1, 1))
    lon[(np.abs(lon) > np.pi) | (np.abs(np.sin(theta) / M) > 1)] = np.nan
    return lon, lat


def relief():
    zip_path = download(RELIEF, 'SR_50M.zip')
    tif = SRC / 'SR_50M.tif'
    if not tif.exists():
        with zipfile.ZipFile(zip_path) as z:
            name = next(n for n in z.namelist() if n.lower().endswith('.tif'))
            tif.write_bytes(z.read(name))
    Image.MAX_IMAGE_PIXELS = None
    src = np.asarray(Image.open(tif).convert('L'))
    h_src, w_src = src.shape

    x_max = np.pi / (M * A1)                      # x at lon=180, lat=0
    y_max = float(equal_earth_y(np.array(np.pi / 3)))  # y at the pole (theta = asin(M) = 60 degrees)
    w = RELIEF_WIDTH
    h = int(round(w * y_max / x_max))
    xs = np.linspace(-x_max, x_max, w, dtype=np.float64)
    out = np.zeros((h, w), np.uint8)
    alpha = np.zeros((h, w), np.uint8)
    for row in range(0, h, 256):  # in strips to keep memory modest
        ys = np.linspace(y_max, -y_max, h)[row:row + 256]
        gx, gy = np.meshgrid(xs, ys)
        lon, lat = equal_earth_invert(gx, gy)
        ok = ~np.isnan(lon)
        px = np.clip(((np.nan_to_num(lon) + np.pi) / (2 * np.pi) * w_src).astype(int), 0, w_src - 1)
        py = np.clip(((np.pi / 2 - lat) / np.pi * h_src).astype(int), 0, h_src - 1)
        out[row:row + 256] = np.where(ok, src[py, px], 0)
        alpha[row:row + 256] = np.where(ok, 255, 0)
    img = Image.merge('LA', [Image.fromarray(out), Image.fromarray(alpha)])
    img.save(OUT / 'relief.webp', quality=80, method=6)
    meta = {'x_max': x_max, 'y_max': y_max, 'width': w, 'height': h}
    (OUT / 'relief.json').write_text(json.dumps(meta))
    print(f'relief.webp {w}x{h}')


def write(name, data):
    path = OUT / name
    path.write_text(json.dumps(data, separators=(',', ':'), ensure_ascii=False))
    print(f'{name:<14} {path.stat().st_size / 1e3:>7.0f} KB')


def main():
    SRC.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    write('rivers.json', slim(geojson('ne_50m_rivers_lake_centerlines'), 'scalerank'))
    write('lakes.json', slim(geojson('ne_50m_lakes'), 'scalerank'))
    write('states.json', slim(geojson('ne_50m_admin_1_states_provinces_lines'), 'scalerank'))
    write('labels.json', labels())
    relief()
    print(f"relief.webp    {(OUT / 'relief.webp').stat().st_size / 1e3:>7.0f} KB")


if __name__ == '__main__':
    main()

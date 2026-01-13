#!/usr/bin/env python3
import os
import math
import glob
import json
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO_ROOT, "docs")

TRACKS_DIR = os.path.join(DOCS, "tracks")
OUT_PATH = os.path.join(DOCS, "data", "tours.geojson")

# ---- helpers ----
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def downsample(coords, max_points=400):
    # keep endpoints + evenly sample in between
    n = len(coords)
    if n <= max_points:
        return coords
    idxs = [0]
    for i in range(1, max_points - 1):
        idxs.append(int(i * (n - 1) / (max_points - 1)))
    idxs.append(n - 1)
    # remove duplicates while preserving order
    seen = set()
    out = []
    for i in idxs:
        if i not in seen:
            out.append(coords[i])
            seen.add(i)
    return out

def parse_gpx_points(gpx_path):
    # minimal GPX parser (no external deps)
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    pts = []
    for trkpt in root.findall(".//gpx:trkpt", ns):
        lat = float(trkpt.attrib["lat"])
        lon = float(trkpt.attrib["lon"])
        pts.append((lon, lat))  # GeoJSON uses [lon, lat]
    if not pts:
        # some files store rtept instead
        for rtept in root.findall(".//gpx:rtept", ns):
            lat = float(rtept.attrib["lat"])
            lon = float(rtept.attrib["lon"])
            pts.append((lon, lat))
    return pts

def track_distance_km(coords_lonlat):
    if len(coords_lonlat) < 2:
        return 0.0
    dist = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords_lonlat, coords_lonlat[1:]):
        dist += haversine_km(lat1, lon1, lat2, lon2)
    return dist

def slug_from_path(path):
    return os.path.splitext(os.path.basename(path))[0]

def title_from_slug(slug):
    return slug.replace("-", " ").replace("_", " ").title()

# ---- main build ----
def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    features = []
    gpx_files = sorted(glob.glob(os.path.join(TRACKS_DIR, "*.gpx")))
    if not gpx_files:
        raise SystemExit(f"No GPX files found in {TRACKS_DIR}")

    for gpx in gpx_files:
        slug = slug_from_path(gpx)
        coords = parse_gpx_points(gpx)
        if len(coords) < 2:
            print(f"Skipping {slug}: not enough points")
            continue

        coords_slim = downsample(coords, max_points=450)
        dist_km = round(track_distance_km(coords), 2)

        # start point for convenience
        start_lon, start_lat = coords[0][0], coords[0][1]

        feature = {
            "type": "Feature",
            "properties": {
                "slug": slug,
                "title": title_from_slug(slug),
                "region": "",           # fill later if you want
                "subtitle": "",
                "activity": "ski_tour", # change per tour later if needed
                "difficulty": "moderate",
                "distance_km": dist_km,
                "vert_m": None,         # optional: fill later
                "time_h": None,         # optional: fill later
                "cover": f"./photos/{slug}/cover.jpg",
                "page": f"./tours/{slug}.html",
                "gpx": f"./tracks/{slug}.gpx",
                "start_lat": start_lat,
                "start_lon": start_lon
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coords_slim
            }
        }
        features.append(feature)

    fc = {"type": "FeatureCollection", "features": features}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} with {len(features)} tours")

if __name__ == "__main__":
    main()

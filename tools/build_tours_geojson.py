#!/usr/bin/env python3
import os
import math
import json
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]   # repo/
DOCS = REPO_ROOT / "docs"
TRACKS_DIR = DOCS / "tracks"
OUT_PATH = DOCS / "data" / "tours.geojson"


# -------------------------
# Mappings for codes -> names
# -------------------------
COUNTRY_MAP = {
    "CAN": "Canada",
    "USA": "United States",
    "AUT": "Austria",
    "DEU": "Germany",
    "CHE": "Switzerland",
}

PROVINCE_MAP = {
    "BC": "British Columbia",
    "AB": "Alberta",
    "YT": "Yukon",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
}

# Keep directions flexible; normalize to lowercase
DIRECTION_MAP = {
    "up": "up",
    "down": "down",
    "loop": "loop",
    "traverse": "traverse",
}


# -------------------------
# Helpers
# -------------------------
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
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


def parse_gpx_points(gpx_path: Path):
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


def slug_from_path(path: Path) -> str:
    return path.stem


def title_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def metadata_from_slug(slug: str) -> dict:
    """
    Parse filenames like:
      Ginpeak_CAN_BC_Whistler_up.gpx

    Robust rule:
      last 4 underscore-separated parts are:
        country_code, province_code, region, direction
      everything before that is the title (can contain underscores)

    Returns a dict with normalized + human-readable fields.
    """
    base = slug.replace("-", "_")  # treat hyphens like underscores for parsing
    parts = [p for p in base.split("_") if p]

    meta = {
        "title": title_from_slug(slug),
        "country_code": "",
        "country": "",
        "province_code": "",
        "province": "",
        "region": "",
        "direction": "",
    }

    # Need at least: title + 4 tokens
    if len(parts) < 5:
        return meta

    title_parts = parts[:-4]
    country_code = parts[-4].upper()
    prov_code = parts[-3].upper()
    region = parts[-2]
    direction = parts[-1].lower()

    # Title: keep any underscores/hyphens in the title part, title-case it
    title_raw = " ".join(title_parts).replace("-", " ").strip()
    meta["title"] = title_raw.title() if title_raw else meta["title"]

    meta["country_code"] = country_code
    meta["country"] = COUNTRY_MAP.get(country_code, country_code)

    meta["province_code"] = prov_code
    meta["province"] = PROVINCE_MAP.get(prov_code, prov_code)

    meta["region"] = region.replace("-", " ").title()
    meta["direction"] = DIRECTION_MAP.get(direction, direction)

    return meta


# -------------------------
# Main build
# -------------------------
def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("REPO_ROOT  =", REPO_ROOT)
    print("TRACKS_DIR =", TRACKS_DIR)
    print("Exists?    =", TRACKS_DIR.is_dir())

    if TRACKS_DIR.is_dir():
        try:
            print("Contents   =", os.listdir(TRACKS_DIR)[:20])
        except Exception:
            pass

    gpx_files = sorted(TRACKS_DIR.glob("*.gpx"))
    if not gpx_files:
        raise SystemExit(f"No GPX files found in {TRACKS_DIR}")

    features = []

    for gpx in gpx_files:
        slug = slug_from_path(gpx)
        meta = metadata_from_slug(slug)

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

                # parsed from filename (robust)
                "title": meta["title"],
                "country_code": meta["country_code"],
                "country": meta["country"],
                "province_code": meta["province_code"],
                "province": meta["province"],
                "region": meta["region"],
                "direction": meta["direction"],

                # you can still override these later manually if needed
                "subtitle": "",
                "activity": "ski_tour",
                "difficulty": "",

                "distance_km": dist_km,
                "vert_m": None,   # optional: fill later
                "time_h": None,   # optional: fill later

                # relative paths used by your web app
                "cover": f"./photos/{slug}/cover.jpg",
                "page": f"./tours/{slug}.html",
                "gpx": f"./tracks/{slug}.gpx",

                "start_lat": start_lat,
                "start_lon": start_lon,
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coords_slim,
            },
        }

        features.append(feature)

    fc = {"type": "FeatureCollection", "features": features}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_PATH} with {len(features)} tours")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import math
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any


# -------------------------
# Repo paths (matches your overview builder)
# -------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]   # repo/
DOCS = REPO_ROOT / "docs"
TRACKS_DIR = DOCS / "tracks"
OVERVIEW_PATH = DOCS / "data" / "tours.geojson"
OUT_DIR = DOCS / "data" / "tours_detail"


# -------------------------
# Mappings (copied from your overview builder)
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

DIRECTION_MAP = {
    "up": "up",
    "down": "down",
    "loop": "loop",
    "traverse": "traverse",
}


# -------------------------
# Geo helpers
# -------------------------
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def track_distance_km(coords_lonlatele: List[Tuple[float, float, Optional[float]]]) -> float:
    if len(coords_lonlatele) < 2:
        return 0.0
    dist = 0.0
    for (lon1, lat1, _e1), (lon2, lat2, _e2) in zip(coords_lonlatele, coords_lonlatele[1:]):
        dist += haversine_km(lat1, lon1, lat2, lon2)
    return dist


def elevation_stats(coords_lonlatele: List[Tuple[float, float, Optional[float]]]) -> Dict[str, Optional[float]]:
    """
    Compute simple ascent/descent stats based on point-to-point differences.
    Uses only points with an elevation value.
    """
    eles = [e for (_lon, _lat, e) in coords_lonlatele if e is not None]
    if len(eles) < 2:
        return {
            "gain_m": None,
            "loss_m": None,
            "min_ele_m": None,
            "max_ele_m": None,
            "start_ele_m": eles[0] if eles else None,
            "end_ele_m": eles[-1] if eles else None,
        }

    gain = 0.0
    loss = 0.0
    prev = None
    for (_lon, _lat, e) in coords_lonlatele:
        if e is None:
            continue
        if prev is not None:
            d = e - prev
            if d > 0:
                gain += d
            elif d < 0:
                loss += -d
        prev = e

    return {
        "gain_m": round(gain, 0),
        "loss_m": round(loss, 0),
        "min_ele_m": round(min(eles), 1),
        "max_ele_m": round(max(eles), 1),
        "start_ele_m": round(eles[0], 1),
        "end_ele_m": round(eles[-1], 1),
    }


# -------------------------
# Slug + metadata parsing (same logic as your overview builder)
# -------------------------
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
    """
    base = slug.replace("-", "_")
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

    if len(parts) < 5:
        return meta

    title_parts = parts[:-4]
    country_code = parts[-4].upper()
    prov_code = parts[-3].upper()
    region = parts[-2]
    direction = parts[-1].lower()

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
# GPX parsing with elevation
# -------------------------
def parse_gpx_points_with_ele(gpx_path: Path) -> List[Tuple[float, float, Optional[float]]]:
    """
    Returns list of (lon, lat, ele_m or None).
    Supports GPX 1.1 trkpt, falls back to rtept.
    """
    ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    pts: List[Tuple[float, float, Optional[float]]] = []

    def parse_pt(pt) -> Tuple[float, float, Optional[float]]:
        lat = float(pt.attrib["lat"])
        lon = float(pt.attrib["lon"])
        ele_node = pt.find("gpx:ele", ns)
        ele = None
        if ele_node is not None and ele_node.text:
            try:
                ele = float(ele_node.text.strip())
            except Exception:
                ele = None
        return (lon, lat, ele)

    for trkpt in root.findall(".//gpx:trkpt", ns):
        pts.append(parse_pt(trkpt))

    if not pts:
        for rtept in root.findall(".//gpx:rtept", ns):
            pts.append(parse_pt(rtept))

    return pts


# -------------------------
# Overview properties (optional)
# -------------------------
def load_overview_by_slug(path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Load docs/data/tours.geojson (if it exists) and map slug -> properties.
    Used so you can override per-tour props (difficulty/activity/subtitle/etc.)
    without re-parsing everything.
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        feats = data.get("features") or []
        out = {}
        for f in feats:
            p = f.get("properties") or {}
            slug = p.get("slug")
            if slug:
                out[str(slug)] = p
        return out
    except Exception:
        return {}


# -------------------------
# Build one detailed geojson per GPX
# -------------------------
def build_detail_feature(slug: str,
                         coords: List[Tuple[float, float, Optional[float]]],
                         overview_props: Dict[str, Any]) -> Dict[str, Any]:

    meta = metadata_from_slug(slug)

    # base props from meta + defaults
    props: Dict[str, Any] = {
        "slug": slug,

        "title": meta["title"],
        "country_code": meta["country_code"],
        "country": meta["country"],
        "province_code": meta["province_code"],
        "province": meta["province"],
        "region": meta["region"],
        "direction": meta["direction"],

        # defaults (can be overridden from overview)
        "subtitle": "",
        "activity": "ski_tour",
        "difficulty": "",

        # relative paths (consistent with overview builder)
        "cover": f"./photos/{slug}/cover.jpg",
        "page": f"./tours/{slug}.html",
        "gpx": f"./tracks/{slug}.gpx",

        # convenience start point
        "start_lon": coords[0][0],
        "start_lat": coords[0][1],
    }

    # stats
    dist_km = round(track_distance_km(coords), 2)
    estats = elevation_stats(coords)

    props["distance_km"] = dist_km
    props.update(estats)

    # Let overview override props you maintain manually
    # (keep it conservative: only override known “user-editable” things)
    for k in ["subtitle", "activity", "difficulty", "vert_m", "time_h",
              "cover", "page", "gpx", "province", "region", "country"]:
        if k in overview_props and overview_props[k] not in (None, ""):
            props[k] = overview_props[k]

    # If you do store a manual vert_m in overview, prefer it,
    # otherwise fall back to computed gain_m (common expectation).
    if props.get("vert_m") in (None, "") and props.get("gain_m") is not None:
        props["vert_m"] = int(props["gain_m"])

    feature = {
        "type": "Feature",
        "properties": props,
        "geometry": {
            "type": "LineString",
            # GeoJSON allows 3D coords: [lon, lat, ele]
            "coordinates": [[lon, lat, ele] for (lon, lat, ele) in coords],
        },
    }
    return feature


def main() -> None:
    print("REPO_ROOT   =", REPO_ROOT)
    print("TRACKS_DIR  =", TRACKS_DIR)
    print("OVERVIEW    =", OVERVIEW_PATH)
    print("OUT_DIR     =", OUT_DIR)

    if not TRACKS_DIR.is_dir():
        raise SystemExit(f"Tracks directory not found: {TRACKS_DIR}")

    gpx_files = sorted(TRACKS_DIR.glob("*.gpx"))
    if not gpx_files:
        raise SystemExit(f"No GPX files found in {TRACKS_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    overview = load_overview_by_slug(OVERVIEW_PATH)

    built = 0
    skipped = 0

    for gpx in gpx_files:
        slug = slug_from_path(gpx)

        coords = parse_gpx_points_with_ele(gpx)
        if len(coords) < 2:
            print(f"Skipping {slug}: not enough points")
            continue

        # Build feature using overview props if available
        oprops = overview.get(slug, {})
        feature = build_detail_feature(slug, coords, oprops)

        fc = {"type": "FeatureCollection", "features": [feature]}
        out_path = OUT_DIR / f"{slug}.geojson"

        # Write only if changed (small speed win)
        new_text = json.dumps(fc, ensure_ascii=False, indent=2)
        if out_path.exists():
            old_text = out_path.read_text(encoding="utf-8")
            if old_text == new_text:
                skipped += 1
                continue

        out_path.write_text(new_text, encoding="utf-8")
        built += 1

    print(f"Built/updated: {built}")
    print(f"Unchanged:     {skipped}")
    print(f"Wrote to:      {OUT_DIR}")


if __name__ == "__main__":
    main()

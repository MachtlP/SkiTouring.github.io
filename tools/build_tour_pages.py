#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import html
import re
from pathlib import Path
from datetime import datetime

# -------------------------
# Paths
# -------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"

DETAIL_GEOJSON_DIR = DOCS / "data" / "tours_detail"
# Optional: overview file can be used for metadata fallback if you want
OVERVIEW_GEOJSON_PATH = DOCS / "data" / "tours.geojson"
TEMPLATE_HTML_PATH = DOCS / "templates" / "tour_page.html"

MD_DIR = DOCS / "tours_md"
MD_TEMPLATE_PATH = MD_DIR / "_template.md"

OUT_DIR = DOCS / "tours"


# -------------------------
# CLI
# -------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Build tour pages from detail GeoJSON files")
    p.add_argument(
        "--rerun",
        action="store_true",
        help="Force overwrite HTML output (rebuild all pages).",
    )
    return p.parse_args()


# -------------------------
# Markdown conversion
# -------------------------
def md_to_html(md_text: str) -> str:
    """
    Convert Markdown -> HTML.
    Uses python-markdown if available; otherwise a small fallback.
    """
    md_text = md_text.replace("\r\n", "\n")

    try:
        import markdown  # type: ignore
        return markdown.markdown(
            md_text,
            extensions=["extra", "tables", "fenced_code", "toc", "sane_lists"],
            output_format="html5",
        )
    except Exception:
        return simple_md_fallback(md_text)


def simple_md_fallback(md_text: str) -> str:
    """
    Fallback converter: headings, paragraphs, bullet lists, links, bold/italic.
    """
    lines = md_text.split("\n")
    out: list[str] = []
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)  # links
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)  # bold
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)  # italic
        return s

    for raw in lines:
        line = raw.rstrip()

        if not line.strip():
            close_ul()
            continue

        if line.startswith("### "):
            close_ul()
            out.append(f"<h3>{inline(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            close_ul()
            out.append(f"<h2>{inline(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            close_ul()
            out.append(f"<h1>{inline(line[2:])}</h1>")
            continue

        if re.match(r"^\s*[-*]\s+", line):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{inline(item)}</li>")
            continue

        close_ul()
        out.append(f"<p>{inline(line)}</p>")

    close_ul()
    return "\n".join(out)


# -------------------------
# Helpers
# -------------------------
def safe_text(v) -> str:
    return "" if v is None else str(v)


def html_escape(v) -> str:
    return html.escape(safe_text(v))


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def as_tour_relative(url: str) -> str:
    """
    Convert docs-root relative URLs like "./tracks/x.gpx" into a path usable from docs/tours/*.html:
      "./tracks/x.gpx" -> "../tracks/x.gpx"
    If url already looks absolute or starts with "../", return as-is.
    """
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if u.startswith("../"):
        return u
    if u.startswith("./"):
        return "../" + u[2:]
    # assume it's already relative to docs root
    return "../" + u.lstrip("/")


def scaffold_markdown_if_missing(md_path: Path, slug: str, props: dict) -> bool:
    """
    If md_path missing, create it from MD_TEMPLATE_PATH.
    Returns True if created.
    """
    if md_path.exists():
        return False

    if not MD_TEMPLATE_PATH.exists():
        raise SystemExit(f"Missing markdown template: {MD_TEMPLATE_PATH}")

    template = MD_TEMPLATE_PATH.read_text(encoding="utf-8")

    replacements = {
        "{{SLUG}}": slug,
        "{{TITLE}}": safe_text(props.get("title", slug)),
        "{{PROVINCE}}": safe_text(props.get("province", "")),
        "{{REGION}}": safe_text(props.get("region", "")),
        "{{COUNTRY}}": safe_text(props.get("country", "")),
        "{{DIRECTION}}": safe_text(props.get("direction", "")),
    }
    for k, v in replacements.items():
        template = template.replace(k, v)

    write_text(md_path, template)
    return True


def fill_template(template_html: str, replacements: dict[str, str]) -> str:
    out = template_html
    for k, v in replacements.items():
        out = out.replace(k, v)
    return out


# -------------------------
# Build
# -------------------------
def main() -> None:
    args = parse_args()
    rerun = bool(args.rerun)

    if not DETAIL_GEOJSON_DIR.exists():
        raise SystemExit(f"Missing detail geojson directory: {DETAIL_GEOJSON_DIR}")
    if not TEMPLATE_HTML_PATH.exists():
        raise SystemExit(f"Missing HTML template: {TEMPLATE_HTML_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)

    # Optional overview metadata (if present). We *don't* require it.
    overview_by_slug: dict[str, dict] = {}
    if OVERVIEW_GEOJSON_PATH.exists():
        try:
            ov = read_json(OVERVIEW_GEOJSON_PATH)
            for f in (ov.get("features") or []):
                p = (f or {}).get("properties") or {}
                s = safe_text(p.get("slug") or "").strip()
                if s:
                    overview_by_slug[s] = p
        except Exception:
            overview_by_slug = {}

    template_html = TEMPLATE_HTML_PATH.read_text(encoding="utf-8")

    detail_files = sorted(DETAIL_GEOJSON_DIR.glob("*.geojson"))
    if not detail_files:
        raise SystemExit(f"No .geojson files found in: {DETAIL_GEOJSON_DIR}")

    built = 0
    skipped = 0
    created_md = 0
    forced = 0

    for gj_path in detail_files:
        slug = gj_path.stem

        gj = read_json(gj_path)

        # Accept either Feature or FeatureCollection (use first feature)
        feature = None
        if isinstance(gj, dict) and gj.get("type") == "Feature":
            feature = gj
        elif isinstance(gj, dict) and gj.get("type") == "FeatureCollection":
            feats = gj.get("features") or []
            if feats:
                feature = feats[0]
        if not feature:
            print(f"Skipping invalid GeoJSON (not a Feature): {gj_path}")
            continue

        props = (feature.get("properties") or {}) if isinstance(feature, dict) else {}
        geom = (feature.get("geometry") or {}) if isinstance(feature, dict) else {}

        # Allow properties.slug to override, but keep filename as fallback
        slug_prop = safe_text(props.get("slug") or "").strip()
        if slug_prop:
            slug = slug_prop

        # Merge in overview metadata (detail props win)
        if slug in overview_by_slug:
            merged = dict(overview_by_slug[slug])
            merged.update(props)
            props = merged

        title = safe_text(props.get("title") or slug).strip() or slug
        province = safe_text(props.get("province") or props.get("province_code") or "").strip()
        region = safe_text(props.get("region") or "").strip()

        # Ensure markdown exists
        md_path = MD_DIR / f"{slug}.md"
        if scaffold_markdown_if_missing(md_path, slug, props):
            created_md += 1

        # Read markdown and convert to HTML
        md_text = md_path.read_text(encoding="utf-8")
        md_html = md_to_html(md_text)

        # If template still expects COORDS_JSON, supply a lightweight [lat,lon] array
        coords_json = "[]"
        try:
            coords = geom.get("coordinates") if isinstance(geom, dict) else None
            if isinstance(coords, list) and coords and isinstance(coords[0], list):
                # coords are usually [[lon,lat,ele], ...]
                latlon = [[c[1], c[0]] for c in coords if isinstance(c, list) and len(c) >= 2]
                coords_json = json.dumps(latlon)
        except Exception:
            coords_json = "[]"

        title_json = json.dumps(title)

        # Links (relative from docs/tours/<slug>.html)
        gpx_url = as_tour_relative(safe_text(props.get("gpx") or f"./tracks/{slug}.gpx"))
        detail_geojson_url = as_tour_relative(f"./data/tours_detail/{slug}.geojson")

        replacements = {
            "{{TITLE}}": html_escape(title),
            "{{PROVINCE}}": html_escape(province) if province else "—",
            "{{REGION}}": html_escape(region) if region else "—",
            "{{GPX_URL}}": html_escape(gpx_url) if gpx_url else "#",
            "{{CONTENT_HTML}}": md_html,
            "{{COORDS_JSON}}": coords_json,
            "{{TITLE_JSON}}": title_json,
            "{{SLUG}}": html_escape(slug),
            "{{DETAIL_GEOJSON_URL}}": html_escape(detail_geojson_url),
        }

        out_path = OUT_DIR / f"{slug}.html"

        # -------- FORCE OVERWRITE MODE --------
        if not rerun:
            # Skip if up-to-date: output newer than template + md + geojson
            latest_input_mtime = max(
                TEMPLATE_HTML_PATH.stat().st_mtime,
                md_path.stat().st_mtime,
                gj_path.stat().st_mtime,
            )
            if out_path.exists() and out_path.stat().st_mtime >= latest_input_mtime:
                skipped += 1
                continue
        else:
            if out_path.exists():
                forced += 1

        page = fill_template(template_html, replacements)
        page = page.replace("{{BUILT_AT}}", datetime.now().strftime("%Y-%m-%d %H:%M"))

        write_text(out_path, page)
        built += 1

    print(f"Created markdown files: {created_md}")
    print(f"Built tour pages: {built}")
    if rerun:
        print(f"Forced overwrites: {forced}")
    else:
        print(f"Skipped (up to date): {skipped}")
    print(f"Detail folder: {DETAIL_GEOJSON_DIR}")
    print(f"Output folder: {OUT_DIR}")
    print(f"Markdown folder: {MD_DIR}")


if __name__ == "__main__":
    main()

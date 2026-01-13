#!/usr/bin/env python3
from __future__ import annotations

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

GEOJSON_PATH = DOCS / "data" / "tours.geojson"
TEMPLATE_HTML_PATH = DOCS / "templates" / "tour_page.html"

MD_DIR = DOCS / "tours_md"
MD_TEMPLATE_PATH = MD_DIR / "_template.md"

OUT_DIR = DOCS / "tours"


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
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)            # links
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)                   # bold
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)                  # italic
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


def newer(a: Path, b: Path) -> bool:
    """True if a is newer than b, or b doesn't exist."""
    if not b.exists():
        return True
    return a.stat().st_mtime > b.stat().st_mtime


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
    if not GEOJSON_PATH.exists():
        raise SystemExit(f"Missing geojson: {GEOJSON_PATH}")
    if not TEMPLATE_HTML_PATH.exists():
        raise SystemExit(f"Missing HTML template: {TEMPLATE_HTML_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MD_DIR.mkdir(parents=True, exist_ok=True)

    gj = read_json(GEOJSON_PATH)
    feats = gj.get("features") or []
    if not feats:
        raise SystemExit("No features in tours.geojson")

    template_html = TEMPLATE_HTML_PATH.read_text(encoding="utf-8")

    built = 0
    skipped = 0
    created_md = 0

    for feat in feats:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}

        slug = props.get("slug") or ""
        if not slug:
            # fallback: derive from "page" like "./tours/<slug>.html"
            page = safe_text(props.get("page", ""))
            slug = Path(page).stem if page else ""
        if not slug:
            print("Skipping feature without slug")
            continue

        title = safe_text(props.get("title") or slug).strip() or slug
        province = safe_text(props.get("province") or props.get("province_code") or "").strip()
        region = safe_text(props.get("region") or "").strip()

        md_path = MD_DIR / f"{slug}.md"
        out_path = OUT_DIR / f"{slug}.html"

        # Scaffold markdown if missing
        if scaffold_markdown_if_missing(md_path, slug, props):
            created_md += 1

        # Build conditions: rebuild if output missing OR inputs newer
        needs = (not out_path.exists()) or newer(GEOJSON_PATH, out_path) or newer(md_path, out_path)
        if not needs:
            skipped += 1
            continue

        md_text = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        md_html = md_to_html(md_text) if md_text.strip() else "<p><em>No notes yet.</em></p>"

        coords = geom.get("coordinates") or []
        coords_json = json.dumps(coords)
        title_json = json.dumps(title)

        gpx_url = as_tour_relative(safe_text(props.get("gpx") or f"./tracks/{slug}.gpx"))

        # Replace placeholders
        replacements = {
            "{{TITLE}}": html_escape(title),
            "{{PROVINCE}}": html_escape(province) if province else "—",
            "{{REGION}}": html_escape(region) if region else "—",
            "{{GPX_URL}}": html_escape(gpx_url) if gpx_url else "#",
            "{{CONTENT_HTML}}": md_html,
            "{{COORDS_JSON}}": coords_json,
            "{{TITLE_JSON}}": title_json,
        }

        page = fill_template(template_html, replacements)

        # nice-to-have: stamp build time (optional placeholder)
        page = page.replace("{{BUILT_AT}}", datetime.now().strftime("%Y-%m-%d %H:%M"))

        write_text(out_path, page)
        built += 1

    print(f"Created markdown files: {created_md}")
    print(f"Built tour pages: {built}")
    print(f"Skipped (up to date): {skipped}")
    print(f"Output folder: {OUT_DIR}")
    print(f"Markdown folder: {MD_DIR}")


if __name__ == "__main__":
    main()

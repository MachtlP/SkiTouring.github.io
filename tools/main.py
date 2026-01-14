#!/usr/bin/env python3
"""
Master build script for the Ski Touring Guide.

Runs, in order:
1) build_tours_geojson.py              (overview)
2) build_tour_detail_geojson.py --rerun (per-tour detail)
3) build_tour_pages.py                 (HTML pages)
"""

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "tools"


def run(cmd: list[str]) -> None:
    """Run a command and abort on failure."""
    print("\n▶ Running:", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n❌ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def main() -> None:
    python = sys.executable  # ensures same venv / interpreter

    run([python, str(SCRIPTS / "build_tours_geojson.py")])

    run([
        python,
        str(SCRIPTS / "build_tour_detail_geojson.py"),
        "--rerun"
    ])

    run([python, str(SCRIPTS / "build_tour_pages.py")])

    print("\n✅ Build pipeline finished successfully")


if __name__ == "__main__":
    main()

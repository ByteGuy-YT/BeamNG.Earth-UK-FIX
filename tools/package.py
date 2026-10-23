#!/usr/bin/env python3
"""Build dist/BeamNG.Earth-<VERSION>.zip, the download for players.

    python3 tools/package.py [--out DIR]

The zip has one top folder, BeamNG.Earth-<VERSION>/, with the mod, the server (no tests, no
__pycache__), the installer and launchers, and the player docs. The version is the VERSION file.
"""

import argparse
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILES = ["install.py", "start.py", "launcher.py", "run_server.bat", "run_server.sh", "README.md", "LICENSE", "CREDITS.md",
         "VERSION", "docs/QUICKSTART.md"]
TREES = ["mod/beamng_earth", "server"]
TOOLS = ["tools/reports.py"]                # user-facing helpers from tools/ (the in-game reports -> GitHub issues)
SKIP_DIRS = {"__pycache__", "tests", ".git", "backups", "probes", "research", ".venv", "dist"}
SKIP_EXT = {".pyc", ".pyo", ".log", ".swp"}
EXECUTABLE = {"run_server.sh", "install.py", "start.py"}


FILES += ["Play UK roads.bat", "docs/UK_ROADS.md", "docs/UK_ROAD_SCREENSHOT_FIXES.md",
          "docs/uk-road-geometry-preview.png", "docs/uk-road-validation.json"]
FILES += ["docs/UK_STREET_DETAILS.md", "docs/uk-street-assets-preview.png", "docs/uk-street-validation.json"]
FILES += ["docs/UK_ROUND2_FIXES.md", "docs/uk-round2-validation.json", "docs/uk-round2-performance.json"]
TOOLS += ["tools/prepare_uk_roads.py", "tools/inspect_uk_roads.py", "tools/make_uk_road_assets.py"]
TOOLS += ["tools/prepare_uk_context.py", "tools/make_uk_street_assets.py"]
TOOLS += ["tools/validate_uk_round2.py"]
FILES += ["docs/UK_MOTORWAY_FIXES.md", "docs/uk-motorway-validation.json",
          "docs/uk-motorway-live-validation.json", "docs/uk-motorway-live.png"]
TOOLS += ["tools/validate_uk_motorways.py"]
FILES += ["docs/WORLD_GEOMETRY_REPAIR.md", "docs/world-geometry-validation.json",
          "docs/world-seam-validation.json", "docs/world-focused-tests.json",
          "docs/world-boston-lane-data.json", "docs/world-boston-road-source.json",
          "docs/world-boston-collision.json", "docs/world-m1-corridor-validation.json",
          "docs/world-boston-lanes.png", "docs/world-m1-profile.png",
          "docs/world-vauxhall-walk.png", "docs/world-stelvio.png",
          ".road-data/osm-extra.sqlite", ".road-data/osm-extra.osm", ".road-data/osm-extra.source.json"]
TOOLS += ["tools/validate_world_geometry.py", "tools/validate_world_seams.py", "tools/prepare_road_attributes.py"]


def version():
    with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as f:
        return f.read().strip()


def collect():
    out = []
    for rel in FILES + TOOLS:
        if not os.path.isfile(os.path.join(ROOT, rel)):
            sys.exit(f"missing: {rel}")
        out.append(rel)
    for tree in TREES:
        for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, tree)):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                if os.path.splitext(name)[1] in SKIP_EXT or name == ".DS_Store":
                    continue
                out.append(os.path.relpath(os.path.join(dirpath, name), ROOT).replace(os.sep, "/"))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"), help="output folder (default: dist/)")
    args = ap.parse_args()
    ver = version()
    top = f"BeamNG.Earth-{ver}"
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, top + ".zip")
    files = collect()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in files:
            src = os.path.join(ROOT, rel)
            info = zipfile.ZipInfo.from_file(src, f"{top}/{rel}")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if os.path.basename(rel) in EXECUTABLE else 0o100644) << 16
            with open(src, "rb") as f:
                z.writestr(info, f.read())
    print(f"{path}: {len(files)} files, {os.path.getsize(path) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

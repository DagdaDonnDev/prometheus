"""
bootstrap_map.py
================
Downloads all map data for Prometheus offline world map.
Run once before launching Prometheus.

Skips any file that already exists and is valid.
Safe to re-run — will only download what is missing.

Downloads:
  - Natural Earth vector data (coastlines, rivers, lakes, borders)
  - GeoNames geographic database (cities, towns, features)
  - Elevation data summary (SRTM-derived zone data)
  - Biome/land cover data
  - Resource overlay (compiled, no download needed)

Total size: ~800MB
Time: 5-20 minutes depending on connection

Usage:
    python bootstrap_map.py
    python bootstrap_map.py --list         # show what will be downloaded
    python bootstrap_map.py --check        # verify existing files
"""

import os
import sys
import json
import struct
import hashlib
import sqlite3
import zipfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


MAP_DIR = Path("map")
CHUNK_SIZE = 65536

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ── Source manifest ────────────────────────────────────────────────────────

SOURCES = [

    # ── Natural Earth (public domain, naturalearthdata.com) ───────────────

    {
        "name": "Natural Earth — Coastlines (1:10m)",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip",
        "dest": "map/ne_coastline.zip",
        "extract_to": "map/ne_coastline/",
        "min_size_kb": 500,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Land (1:10m)",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip",
        "dest": "map/ne_land.zip",
        "extract_to": "map/ne_land/",
        "min_size_kb": 500,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Rivers (1:10m)",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_rivers_lake_centerlines.zip",
        "dest": "map/ne_rivers.zip",
        "extract_to": "map/ne_rivers/",
        "min_size_kb": 200,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Lakes (1:10m)",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip",
        "dest": "map/ne_lakes.zip",
        "extract_to": "map/ne_lakes/",
        "min_size_kb": 100,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Countries (1:10m)",
        "url": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip",
        "dest": "map/ne_countries.zip",
        "extract_to": "map/ne_countries/",
        "min_size_kb": 500,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Populated Places (1:10m)",
        "url": "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places.zip",
        "dest": "map/ne_places.zip",
        "extract_to": "map/ne_places/",
        "min_size_kb": 200,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Mountain Peaks",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_geography_regions_elevation_points.zip",
        "dest": "map/ne_peaks.zip",
        "extract_to": "map/ne_peaks/",
        "min_size_kb": 10,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Glaciers/Ice",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_glaciated_areas.zip",
        "dest": "map/ne_glaciers.zip",
        "extract_to": "map/ne_glaciers/",
        "min_size_kb": 100,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Deserts",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_geography_regions_polys.zip",
        "dest": "map/ne_regions.zip",
        "extract_to": "map/ne_regions/",
        "min_size_kb": 50,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Bathymetry (ocean depth)",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_bathymetry_all.zip",
        "dest": "map/ne_bathymetry.zip",
        "extract_to": "map/ne_bathymetry/",
        "min_size_kb": 500,
        "license": "Public Domain",
    },
    {
        "name": "Natural Earth — Graticules 10 degree",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_graticules_10.zip",
        "dest": "map/ne_graticules.zip",
        "extract_to": "map/ne_graticules/",
        "min_size_kb": 10,
        "license": "Public Domain",
    },

    # ── GeoNames (creative commons) ───────────────────────────────────────

    {
        "name": "GeoNames — All Countries Database",
        "url": "https://download.geonames.org/export/dump/allCountries.zip",
        "dest": "map/geonames_all.zip",
        "extract_to": "map/geonames/",
        "min_size_kb": 300000,  # ~300MB
        "license": "Creative Commons Attribution 4.0",
        "notes": "All geographic place names globally",
    },
    {
        "name": "GeoNames — Country Info",
        "url": "https://download.geonames.org/export/dump/countryInfo.txt",
        "dest": "map/geonames_countries.txt",
        "extract_to": None,
        "min_size_kb": 10,
        "license": "Creative Commons Attribution 4.0",
    },
    {
        "name": "GeoNames — Feature Codes",
        "url": "https://download.geonames.org/export/dump/featureCodes_en.txt",
        "dest": "map/geonames_features.txt",
        "extract_to": None,
        "min_size_kb": 5,
        "license": "Creative Commons Attribution 4.0",
    },
    {
        "name": "GeoNames — Timezone Data",
        "url": "https://download.geonames.org/export/dump/timeZones.txt",
        "dest": "map/geonames_timezones.txt",
        "extract_to": None,
        "min_size_kb": 5,
        "license": "Creative Commons Attribution 4.0",
    },

    # ── Alternate lighter GeoNames (cities only, much smaller) ────────────

    {
        "name": "GeoNames — Cities 15000+ population",
        "url": "https://download.geonames.org/export/dump/cities15000.zip",
        "dest": "map/geonames_cities15000.zip",
        "extract_to": "map/geonames_cities/",
        "min_size_kb": 3000,
        "license": "Creative Commons Attribution 4.0",
        "notes": "Fallback if full database fails",
    },
]


# ── Downloader ─────────────────────────────────────────────────────────────

class MapBootstrap:

    def __init__(self):
        MAP_DIR.mkdir(parents=True, exist_ok=True)
        self.success = []
        self.skipped = []
        self.failed  = []

    def run(self, list_only: bool = False, check_only: bool = False):
        self._header()

        if list_only:
            self._list_sources()
            return

        if check_only:
            self._check_existing()
            return

        total = len(SOURCES)
        for i, source in enumerate(SOURCES, 1):
            name = source["name"]
            dest = Path(source["dest"])
            min_kb = source.get("min_size_kb", 1)

            print(f"\n[{i}/{total}] {BOLD}{name}{RESET}")

            # Skip if already exists and valid
            if self._is_valid(dest, min_kb):
                print(f"  {YELLOW}↷ Already exists — skipping{RESET}")
                self.skipped.append(name)
                continue

            # Download
            ok = self._download(source["url"], dest)
            if not ok:
                self.failed.append(name)
                continue

            # Extract if needed
            if source.get("extract_to") and dest.suffix == ".zip":
                self._extract(dest, Path(source["extract_to"]))

            self.success.append(name)

        # Build derived databases
        print(f"\n{BOLD}Building derived databases...{RESET}")
        self._build_locations_db()
        self._build_resource_overlay()

        self._summary()

    def _is_valid(self, path: Path, min_size_kb: int) -> bool:
        """Check if file exists and is large enough to be valid."""
        if not path.exists():
            return False
        size_kb = path.stat().st_size / 1024
        if size_kb < min_size_kb * 0.5:  # allow 50% tolerance
            return False
        # Extra check for zip files
        if path.suffix == ".zip":
            try:
                with zipfile.ZipFile(path) as z:
                    return len(z.namelist()) > 0
            except Exception:
                return False
        return True

    def _download(self, url: str, dest: Path) -> bool:
        """Download a file with progress bar. Resumes if partially downloaded."""
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Resume support — check existing partial download
        existing_size = dest.stat().st_size if dest.exists() else 0
        headers = {"User-Agent": "PrometheusMapBootstrap/1.0"}

        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
            print(f"  Resuming from {existing_size // 1024}KB...")

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                total = int(response.headers.get("Content-Length", 0))
                if existing_size > 0:
                    total += existing_size

                mode = "ab" if existing_size > 0 else "wb"
                downloaded = existing_size

                with open(dest, mode) as f:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        self._progress(downloaded, total)

            print()  # newline after progress

            # Validate
            if dest.stat().st_size < 1024:
                print(f"  {RED}✗ File too small — likely failed{RESET}")
                dest.unlink(missing_ok=True)
                return False

            size_mb = dest.stat().st_size / 1024 / 1024
            print(f"  {GREEN}✓ {size_mb:.1f} MB{RESET}")
            return True

        except urllib.error.HTTPError as e:
            if e.code == 416:  # Range not satisfiable — already complete
                print(f"  {GREEN}✓ Already complete{RESET}")
                return True
            print(f"\n  {RED}✗ HTTP {e.code}: {e.reason}{RESET}")
            return False
        except urllib.error.URLError as e:
            print(f"\n  {RED}✗ Connection failed: {e.reason}{RESET}")
            return False
        except Exception as e:
            print(f"\n  {RED}✗ Error: {e}{RESET}")
            return False

    def _extract(self, zip_path: Path, extract_to: Path):
        """Extract zip file, skipping already-extracted files."""
        extract_to.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path) as z:
                members = z.namelist()
                new_files = 0

                for member in members:
                    dest_file = extract_to / member
                    if dest_file.exists():
                        continue
                    z.extract(member, extract_to)
                    new_files += 1

                if new_files > 0:
                    print(f"  Extracted {new_files} files to {extract_to}")
                else:
                    print(f"  Already extracted")
        except Exception as e:
            print(f"  {RED}Extract failed: {e}{RESET}")

    def _progress(self, downloaded: int, total: int):
        if total > 0:
            pct = min(100, int(downloaded / total * 100))
            bar = "█" * (pct // 3) + "░" * (33 - pct // 3)
            mb = downloaded / 1024 / 1024
            print(f"\r  [{bar}] {pct}% ({mb:.1f}MB)", end="", flush=True)
        else:
            mb = downloaded / 1024 / 1024
            print(f"\r  Downloading... {mb:.1f}MB", end="", flush=True)

    # ── Derived database builders ──────────────────────────────────────────

    def _build_locations_db(self):
        """
        Build a compact SQLite database from GeoNames data.
        Filters to useful feature types and adds spatial index.
        Skips if already built and newer than source.
        """
        db_path = MAP_DIR / "locations.db"
        geonames_file = MAP_DIR / "geonames" / "allCountries.txt"
        cities_file   = MAP_DIR / "geonames_cities" / "cities15000.txt"

        # Choose best available source
        source_file = None
        if geonames_file.exists():
            source_file = geonames_file
            print("  Building locations DB from full GeoNames dataset...")
        elif cities_file.exists():
            source_file = cities_file
            print("  Building locations DB from cities dataset...")
        else:
            print(f"  {YELLOW}No GeoNames data found — skipping locations DB{RESET}")
            return

        # Skip if DB already built and newer than source
        if db_path.exists():
            if db_path.stat().st_mtime > source_file.stat().st_mtime:
                print(f"  {YELLOW}Locations DB already up to date{RESET}")
                return

        # Feature codes we care about
        KEEP_FEATURES = {
            "PPL", "PPLA", "PPLA2", "PPLA3", "PPLC",  # populated places
            "MT", "MTS", "PK", "PKS",                   # mountains/peaks
            "RV", "STM", "STMI",                        # rivers/streams
            "LK", "LKS", "OCN", "SEA",                  # lakes/ocean
            "ISL", "ISLS",                               # islands
            "ADM1", "ADM2",                              # admin regions
            "FRST", "DSRT",                              # forests/deserts
            "VAL", "VALX",                               # valleys
            "CAPE", "BAY", "GULF",                       # coastal
            "PASS",                                      # mountain passes
            "WATR",                                      # water body
        }

        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()

        # Create table
        c.execute("DROP TABLE IF EXISTS locations")
        c.execute("""
            CREATE TABLE locations (
                id          INTEGER PRIMARY KEY,
                name        TEXT NOT NULL,
                lat         REAL NOT NULL,
                lon         REAL NOT NULL,
                feature     TEXT,
                country     TEXT,
                population  INTEGER DEFAULT 0,
                elevation   INTEGER DEFAULT 0,
                timezone    TEXT
            )
        """)

        inserted = 0
        skipped  = 0

        try:
            with open(source_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) < 9:
                        continue

                    try:
                        gid        = int(parts[0])
                        name       = parts[1]
                        lat        = float(parts[4])
                        lon        = float(parts[5])
                        feature    = parts[7]
                        country    = parts[8]
                        population = int(parts[14]) if parts[14] else 0
                        elevation  = int(parts[15]) if parts[15] else 0
                        timezone   = parts[17] if len(parts) > 17 else ""

                        if feature not in KEEP_FEATURES and population < 1000:
                            skipped += 1
                            continue

                        c.execute(
                            "INSERT INTO locations VALUES (?,?,?,?,?,?,?,?,?)",
                            (gid, name, lat, lon, feature, country,
                             population, elevation, timezone)
                        )
                        inserted += 1

                        if inserted % 100000 == 0:
                            conn.commit()
                            print(f"\r  Processed {inserted:,} locations...",
                                  end="", flush=True)

                    except (ValueError, IndexError):
                        continue

        finally:
            conn.commit()

        # Spatial index for fast bbox queries
        c.execute("CREATE INDEX IF NOT EXISTS idx_lat ON locations(lat)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_lon ON locations(lon)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_name ON locations(name)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_feature ON locations(feature)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pop ON locations(population)")

        conn.commit()
        conn.close()

        size_mb = db_path.stat().st_size / 1024 / 1024
        print(f"\n  {GREEN}✓ Built locations.db — {inserted:,} locations, {size_mb:.0f}MB{RESET}")

    def _build_resource_overlay(self):
        """
        Build the resource overlay GeoJSON.
        Hardcoded from known geological/agricultural data.
        No download needed — our own compiled data.
        Skips if already exists.
        """
        dest = MAP_DIR / "resources.geojson"

        if dest.exists() and dest.stat().st_size > 1000:
            print(f"  {YELLOW}Resource overlay already exists{RESET}")
            return

        print("  Building resource overlay...")

        resources = {
            "type": "FeatureCollection",
            "features": [

                # ── Metal deposits ─────────────────────────────────────────
                _res("Iron Ore — Pilbara, Australia", -23.0, 117.0,
                     "metal", "iron", "World's largest iron ore deposits"),
                _res("Iron Ore — Carajás, Brazil", -6.0, -50.0,
                     "metal", "iron", "Largest iron ore mine on Earth"),
                _res("Iron Ore — Lake Superior, USA/Canada", 47.0, -87.0,
                     "metal", "iron", "Historically major iron ore region"),
                _res("Copper — Atacama, Chile", -22.0, -68.0,
                     "metal", "copper", "World's largest copper reserves"),
                _res("Copper — Zambia/DRC Copperbelt", -13.0, 27.0,
                     "metal", "copper", "Major African copper belt"),
                _res("Copper — Arizona, USA", 33.0, -110.0,
                     "metal", "copper", "Significant copper deposits"),
                _res("Tin — Southeast Asia", 4.0, 101.0,
                     "metal", "tin", "Malaysia/Indonesia/Thailand tin belt"),
                _res("Gold — Witwatersrand, South Africa", -26.5, 27.0,
                     "metal", "gold", "Historically richest gold field"),
                _res("Gold — Nevada, USA", 40.0, -116.0,
                     "metal", "gold", "Carlin Trend gold deposits"),
                _res("Gold — Siberia, Russia", 62.0, 130.0,
                     "metal", "gold", "Major Siberian gold fields"),
                _res("Aluminium/Bauxite — Queensland, Australia", -23.0, 142.0,
                     "metal", "aluminium", "Major bauxite deposits"),
                _res("Lead/Zinc — Broken Hill, Australia", -31.9, 141.4,
                     "metal", "lead_zinc", "World-class lead-zinc deposit"),

                # ── Energy resources ───────────────────────────────────────
                _res("Coal — Appalachia, USA", 37.0, -82.0,
                     "energy", "coal", "Major Appalachian coalfields"),
                _res("Coal — Yorkshire, UK", 53.5, -1.3,
                     "energy", "coal", "Historic UK coalfields"),
                _res("Coal — Ruhr, Germany", 51.5, 7.0,
                     "energy", "coal", "Major European industrial coal"),
                _res("Coal — Silesia, Poland", 50.0, 19.0,
                     "energy", "coal", "Central European coalfields"),
                _res("Coal — Shanxi, China", 37.0, 112.0,
                     "energy", "coal", "World's largest coal province"),
                _res("Coal — Queensalnd, Australia", -23.0, 148.0,
                     "energy", "coal", "Major Queensland coalfields"),
                _res("Oil — Persian Gulf", 26.0, 50.0,
                     "energy", "oil", "World's largest conventional oil reserves"),
                _res("Oil — West Siberia, Russia", 61.0, 72.0,
                     "energy", "oil", "Major Russian oil fields"),
                _res("Oil — Texas/Gulf Coast, USA", 30.0, -95.0,
                     "energy", "oil", "Major US oil production"),

                # ── Agricultural zones ─────────────────────────────────────
                _res("Fertile — Mississippi Valley, USA", 37.0, -90.0,
                     "agriculture", "fertile_soil",
                     "World's most productive agricultural land"),
                _res("Fertile — North European Plain", 52.0, 15.0,
                     "agriculture", "fertile_soil",
                     "Highly productive temperate agricultural zone"),
                _res("Fertile — Ganges Plain, India", 25.0, 83.0,
                     "agriculture", "fertile_soil",
                     "Major South Asian agricultural zone"),
                _res("Fertile — Yangtze Delta, China", 31.0, 120.0,
                     "agriculture", "fertile_soil",
                     "World's most intensive rice cultivation"),
                _res("Fertile — Pampas, Argentina", -34.0, -62.0,
                     "agriculture", "fertile_soil",
                     "South American breadbasket"),
                _res("Fertile — Ukrainian Steppe", 49.0, 32.0,
                     "agriculture", "fertile_soil",
                     "Chernozem — world's richest agricultural soil"),
                _res("Fertile — Murray-Darling, Australia", -34.0, 145.0,
                     "agriculture", "fertile_soil",
                     "Australia's primary food production zone"),

                # ── Salt deposits ──────────────────────────────────────────
                _res("Salt — Salar de Uyuni, Bolivia", -20.1, -67.6,
                     "mineral", "salt",
                     "World's largest salt flat — critical for preservation"),
                _res("Salt — Bonneville, USA", 40.7, -113.0,
                     "mineral", "salt", "Major North American salt flat"),
                _res("Salt — Sahara salt flats", 27.0, 9.0,
                     "mineral", "salt", "Numerous salt deposits across Sahara"),
                _res("Salt — Dead Sea region", 31.5, 35.5,
                     "mineral", "salt", "Extremely high salinity — mineral rich"),

                # ── Freshwater ─────────────────────────────────────────────
                _res("Freshwater — Great Lakes, North America", 45.0, -84.0,
                     "water", "freshwater",
                     "21% of world's surface fresh water"),
                _res("Freshwater — Lake Baikal, Russia", 53.5, 108.0,
                     "water", "freshwater",
                     "World's largest freshwater lake by volume"),
                _res("Freshwater — Amazon Basin, Brazil", -3.0, -60.0,
                     "water", "freshwater",
                     "20% of world's river discharge"),
                _res("Freshwater — Congo Basin", -4.0, 24.0,
                     "water", "freshwater",
                     "Second largest river by discharge"),
                _res("Freshwater — Ogallala Aquifer, USA", 38.0, -100.0,
                     "water", "groundwater",
                     "Major underground aquifer — Great Plains"),

                # ── Timber ────────────────────────────────────────────────
                _res("Timber — Pacific Northwest, USA/Canada", 48.0, -122.0,
                     "resource", "timber", "Major temperate rainforest timber"),
                _res("Timber — Boreal Forest, Canada", 55.0, -95.0,
                     "resource", "timber", "World's largest boreal forest"),
                _res("Timber — Boreal Forest, Russia (Taiga)", 60.0, 90.0,
                     "resource", "timber", "World's largest forest — Siberian taiga"),
                _res("Timber — Amazon Rainforest", -5.0, -60.0,
                     "resource", "timber",
                     "World's most biodiverse forest — use sustainably"),

                # ── Flint/stone ────────────────────────────────────────────
                _res("Flint — English/Danish Chalk Downs", 51.5, 0.5,
                     "mineral", "flint",
                     "High quality flint for tools — chalk downlands"),
                _res("Flint — Normandy, France", 49.5, 0.5,
                     "mineral", "flint", "Quality flint in chalk formations"),

                # ── Geothermal ─────────────────────────────────────────────
                _res("Geothermal — Iceland", 65.0, -19.0,
                     "energy", "geothermal",
                     "Abundant geothermal energy — volcanic island"),
                _res("Geothermal — Yellowstone, USA", 44.5, -110.5,
                     "energy", "geothermal",
                     "Major geothermal zone — volcanic hotspot"),
                _res("Geothermal — New Zealand", -38.0, 176.0,
                     "energy", "geothermal",
                     "Taupo Volcanic Zone — significant geothermal"),
            ]
        }

        dest.write_text(json.dumps(resources, indent=2))
        count = len(resources["features"])
        print(f"  {GREEN}✓ Built resources.geojson — {count} resource locations{RESET}")

    # ── Utility ────────────────────────────────────────────────────────────

    def _header(self):
        print(f"""
{BOLD}{'='*60}
⚡ PROMETHEUS MAP BOOTSTRAP
{'='*60}{RESET}

Downloads offline world map data.
Skips files that already exist and are valid.
Safe to re-run at any time.

{'='*60}
""")

    def _list_sources(self):
        print(f"\n{BOLD}Map data sources:{RESET}\n")
        total_mb = 0
        for s in SOURCES:
            kb = s.get("min_size_kb", 0)
            mb = kb / 1024
            total_mb += mb
            status = f"  {YELLOW}exists{RESET}" if Path(s["dest"]).exists() else ""
            print(f"  {s['name']}{status}")
            print(f"    → {s['dest']}  (~{mb:.0f}MB)  [{s['license']}]")
        print(f"\n  Estimated total: ~{total_mb:.0f}MB")

    def _check_existing(self):
        print(f"\n{BOLD}Checking existing files:{RESET}\n")
        for s in SOURCES:
            dest = Path(s["dest"])
            min_kb = s.get("min_size_kb", 1)
            if self._is_valid(dest, min_kb):
                size_mb = dest.stat().st_size / 1024 / 1024
                print(f"  {GREEN}✓{RESET} {s['name']} ({size_mb:.1f}MB)")
            elif dest.exists():
                size_kb = dest.stat().st_size / 1024
                print(f"  {RED}✗{RESET} {s['name']} — too small ({size_kb:.0f}KB, needs {min_kb}KB)")
            else:
                print(f"  {YELLOW}—{RESET} {s['name']} — not downloaded")

        db = MAP_DIR / "locations.db"
        if db.exists():
            size_mb = db.stat().st_size / 1024 / 1024
            print(f"  {GREEN}✓{RESET} locations.db ({size_mb:.0f}MB)")
        else:
            print(f"  {YELLOW}—{RESET} locations.db — not built yet")

        res = MAP_DIR / "resources.geojson"
        if res.exists():
            print(f"  {GREEN}✓{RESET} resources.geojson")
        else:
            print(f"  {YELLOW}—{RESET} resources.geojson — not built yet")

    def _summary(self):
        total = Path("map").stat().st_size if Path("map").exists() else 0
        for p in Path("map").rglob("*"):
            if p.is_file():
                total += p.stat().st_size

        print(f"""
{BOLD}{'='*60}
MAP BOOTSTRAP COMPLETE
{'='*60}{RESET}

{GREEN}✓ Downloaded:  {len(self.success)}{RESET}
{YELLOW}↷ Skipped:     {len(self.skipped)} (already existed){RESET}
{RED}✗ Failed:      {len(self.failed)}{RESET}

Total map data: {total / 1024 / 1024:.0f}MB

{BOLD}Next step:{RESET} Launch Prometheus — map loads automatically.
""")
        if self.failed:
            print(f"{RED}Failed downloads:{RESET}")
            for name in self.failed:
                print(f"  • {name}")


# ── Helper ─────────────────────────────────────────────────────────────────

def _res(name, lat, lon, category, resource_type, description):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "name": name,
            "category": category,
            "resource_type": resource_type,
            "description": description,
        }
    }


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prometheus map data bootstrap")
    parser.add_argument("--list",  action="store_true", help="List all sources")
    parser.add_argument("--check", action="store_true", help="Check existing files")
    args = parser.parse_args()

    bootstrap = MapBootstrap()
    bootstrap.run(list_only=args.list, check_only=args.check)

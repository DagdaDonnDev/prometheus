"""
Map Engine
==========
Loads and queries all offline map data.
Serves vector geometry for rendering.
Handles location lookup, reverse geocoding, resource queries.

No internet required after tools/bootstrap_map.py has been run.
"""

import json
import math
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass


MAP_DIR = Path("map")


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class Location:
    name:       str
    lat:        float
    lon:        float
    feature:    str
    country:    str
    population: int
    elevation:  int

@dataclass
class Resource:
    name:          str
    lat:           float
    lon:           float
    category:      str
    resource_type: str
    description:   str

@dataclass
class MapBounds:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @classmethod
    def from_centre(cls, lat: float, lon: float, radius_deg: float):
        return cls(
            min_lat=lat - radius_deg,
            max_lat=lat + radius_deg,
            min_lon=lon - radius_deg,
            max_lon=lon + radius_deg,
        )


# ── Biome definitions ──────────────────────────────────────────────────────

# Simplified biome classification from lat/lon
# Real biome data would come from land cover raster — this is a good approximation
BIOME_RULES = [
    # (lat_min, lat_max, description, color_hint)
    (66.5,  90.0, "Arctic / Tundra",           "#e8f4f8"),
    (55.0,  66.5, "Boreal Forest (Taiga)",      "#2d6a2d"),
    (40.0,  55.0, "Temperate Forest",           "#4a8a4a"),
    (30.0,  40.0, "Mediterranean / Grassland",  "#c8b560"),
    (23.5,  30.0, "Subtropical Desert",         "#e8d080"),
    (10.0,  23.5, "Tropical Savanna",           "#8ab840"),
    (-10.0, 10.0, "Tropical Rainforest",        "#1a6a1a"),
    (-23.5,-10.0, "Tropical Savanna",           "#8ab840"),
    (-30.0,-23.5, "Subtropical Desert",         "#e8d080"),
    (-40.0,-30.0, "Mediterranean / Grassland",  "#c8b560"),
    (-55.0,-40.0, "Temperate Forest",           "#4a8a4a"),
    (-66.5,-55.0, "Subantarctic",               "#9ab8b8"),
    (-90.0,-66.5, "Antarctic",                  "#ffffff"),
]

SURVIVAL_CONTEXT = {
    "Arctic / Tundra": {
        "water": "Melt ice/snow — never eat raw. Boil everything.",
        "food": "Hunt caribou, fish, seals. Plants minimal in summer only.",
        "shelter": "Insulation from ground critical. Snow shelter viable.",
        "hazards": "Hypothermia, frostbite, polar bear (Arctic), whiteout.",
        "season": "Extreme light/dark cycles. Winter survival is primary challenge.",
    },
    "Boreal Forest (Taiga)": {
        "water": "Rivers and lakes abundant. Always purify.",
        "food": "Large game (moose, deer, bear), fish, berries in summer, pine inner bark.",
        "shelter": "Timber abundant. Insulation critical in winter.",
        "hazards": "Hypothermia, bears, wolves, dense navigation difficulty.",
        "season": "Long cold winters. Short productive summer.",
    },
    "Temperate Forest": {
        "water": "Rivers and streams common. Purify all surface water.",
        "food": "Deer, rabbit, fish, acorns, berries, nettles, dandelion.",
        "shelter": "Timber abundant. Four seasons — prepare for cold winters.",
        "hazards": "Lyme disease (ticks), mild flooding, occasional severe storms.",
        "season": "Four distinct seasons. Best survival conditions globally.",
    },
    "Mediterranean / Grassland": {
        "water": "Seasonal — wet winters, dry summers. Find springs and wells.",
        "food": "Grains, olives, grapes naturally. Game moderate.",
        "shelter": "Dry stone or adobe excellent in this climate.",
        "hazards": "Summer drought and fire risk. Flash floods in winter.",
        "season": "Ideal agriculture zone. Mild enough year-round.",
    },
    "Subtropical Desert": {
        "water": "CRITICAL PRIORITY. Dry riverbeds, dew collection, deep wells.",
        "food": "Prickly pear, mesquite, agave. Camels/reptiles. Hunt at night.",
        "shelter": "Shade is survival. Underground or rock overhangs.",
        "hazards": "Heat stroke, dehydration, flash floods, venomous animals.",
        "season": "Extreme heat in summer. Navigate and work at night.",
    },
    "Tropical Savanna": {
        "water": "Seasonal rivers. Follow animal trails to water.",
        "food": "Large game abundant, root vegetables, fruit trees near water.",
        "shelter": "Elevation for airflow. Thorn barriers against predators.",
        "hazards": "Malaria, large predators, seasonal flooding, heat.",
        "season": "Wet/dry season cycle. Plan around water availability.",
    },
    "Tropical Rainforest": {
        "water": "Abundant but ALWAYS purify. Parasites are serious risk.",
        "food": "Extraordinary diversity. Learn local plants carefully.",
        "shelter": "Elevated off ground. Rainproof essential.",
        "hazards": "Infections, parasites, snakes, insects, navigation loss.",
        "season": "Year-round warmth. Wet/less wet rather than seasons.",
    },
    "Subantarctic": {
        "water": "Glacial melt. Purify.",
        "food": "Seabirds, fish, seals on coast. Minimal plant food.",
        "shelter": "Wind protection critical. Cold and wet.",
        "hazards": "Hypothermia, wind exposure, isolation.",
        "season": "Harsh year-round. Summer brief.",
    },
    "Antarctic": {
        "water": "Melt snow/ice. Never eat raw.",
        "food": "Coastal: fish, seals, penguins. Inland: nothing.",
        "shelter": "Snow construction essential.",
        "hazards": "Extreme cold, blizzards, crevasses.",
        "season": "Survival only. No long-term habitation without resupply.",
    },
}


# ── Map engine ─────────────────────────────────────────────────────────────

class MapEngine:
    """
    Core map data engine.
    Loads vector data, serves queries, handles location lookup.
    """

    def __init__(self):
        self._locations_db: Optional[sqlite3.Connection] = None
        self._resources: List[Resource] = []
        self._geodata: Dict[str, Any] = {}
        self.ready = False
        self._load()

    def _load(self):
        """Load all available map data."""
        self._load_locations_db()
        self._load_resources()
        self._load_geodata()
        self.ready = True

    def _load_locations_db(self):
        db_path = MAP_DIR / "locations.db"
        if db_path.exists():
            try:
                self._locations_db = sqlite3.connect(
                    str(db_path),
                    check_same_thread=False
                )
                self._locations_db.row_factory = sqlite3.Row
            except Exception:
                self._locations_db = None

    def _load_resources(self):
        res_path = MAP_DIR / "resources.geojson"
        if res_path.exists():
            try:
                data = json.loads(res_path.read_text())
                for feat in data.get("features", []):
                    props = feat["properties"]
                    coords = feat["geometry"]["coordinates"]
                    self._resources.append(Resource(
                        name=props["name"],
                        lat=coords[1],
                        lon=coords[0],
                        category=props["category"],
                        resource_type=props["resource_type"],
                        description=props["description"],
                    ))
            except Exception:
                pass

    def _load_geodata(self):
        """Load lightweight vector data into memory for rendering."""
        # Load country outlines (simplified)
        countries_dir = MAP_DIR / "ne_countries"
        if countries_dir.exists():
            shp = list(countries_dir.glob("*.shp"))
            if shp:
                try:
                    self._geodata["countries"] = shp[0]
                except Exception:
                    pass

    # ── Location queries ───────────────────────────────────────────────────

    def search_locations(
        self,
        query: str,
        limit: int = 10
    ) -> List[Location]:
        """Search for places by name."""
        if not self._locations_db:
            return []

        try:
            rows = self._locations_db.execute(
                """SELECT * FROM locations
                   WHERE name LIKE ?
                   ORDER BY population DESC
                   LIMIT ?""",
                (f"%{query}%", limit)
            ).fetchall()
            return [self._row_to_location(r) for r in rows]
        except Exception:
            return []

    def reverse_geocode(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50
    ) -> Optional[Location]:
        """Find nearest named place to coordinates."""
        if not self._locations_db:
            return None

        # Convert km to rough degrees
        radius_deg = radius_km / 111.0

        try:
            rows = self._locations_db.execute(
                """SELECT *, (
                       (lat - ?) * (lat - ?) +
                       (lon - ?) * (lon - ?)
                   ) as dist
                   FROM locations
                   WHERE lat BETWEEN ? AND ?
                   AND lon BETWEEN ? AND ?
                   ORDER BY dist ASC
                   LIMIT 1""",
                (lat, lat, lon, lon,
                 lat - radius_deg, lat + radius_deg,
                 lon - radius_deg, lon + radius_deg)
            ).fetchone()

            return self._row_to_location(rows) if rows else None
        except Exception:
            return None

    def locations_in_bounds(
        self,
        bounds: MapBounds,
        limit: int = 200,
        min_population: int = 0
    ) -> List[Location]:
        """Get all locations within a bounding box."""
        if not self._locations_db:
            return []

        try:
            rows = self._locations_db.execute(
                """SELECT * FROM locations
                   WHERE lat BETWEEN ? AND ?
                   AND lon BETWEEN ? AND ?
                   AND population >= ?
                   ORDER BY population DESC
                   LIMIT ?""",
                (bounds.min_lat, bounds.max_lat,
                 bounds.min_lon, bounds.max_lon,
                 min_population, limit)
            ).fetchall()
            return [self._row_to_location(r) for r in rows]
        except Exception:
            return []

    def _row_to_location(self, row) -> Location:
        return Location(
            name=row["name"],
            lat=row["lat"],
            lon=row["lon"],
            feature=row["feature"] or "",
            country=row["country"] or "",
            population=row["population"] or 0,
            elevation=row["elevation"] or 0,
        )

    # ── Resource queries ───────────────────────────────────────────────────

    def resources_in_bounds(self, bounds: MapBounds) -> List[Resource]:
        """Get resources within a bounding box."""
        return [
            r for r in self._resources
            if bounds.min_lat <= r.lat <= bounds.max_lat
            and bounds.min_lon <= r.lon <= bounds.max_lon
        ]

    def nearest_resources(
        self,
        lat: float,
        lon: float,
        radius_km: float = 500,
        categories: Optional[List[str]] = None
    ) -> List[Resource]:
        """Find nearest resources to a point."""
        results = []
        for r in self._resources:
            if categories and r.category not in categories:
                continue
            dist = self._haversine(lat, lon, r.lat, r.lon)
            if dist <= radius_km:
                results.append((dist, r))

        results.sort(key=lambda x: x[0])
        return [r for _, r in results]

    # ── Biome and survival context ─────────────────────────────────────────

    def get_biome(self, lat: float, lon: float) -> str:
        """Get biome name for coordinates."""
        for lat_min, lat_max, biome, _ in BIOME_RULES:
            if lat_min <= lat <= lat_max:
                return biome
        return "Unknown"

    def get_survival_context(self, lat: float, lon: float) -> Dict:
        """
        Get survival-relevant context for a location.
        Returns biome info, nearby resources, and survival notes.
        """
        biome = self.get_biome(lat, lon)
        context = SURVIVAL_CONTEXT.get(biome, {})

        # Get nearby location name
        nearest = self.reverse_geocode(lat, lon, radius_km=100)

        # Get nearby resources
        resources = self.nearest_resources(lat, lon, radius_km=300)
        resource_summary = {}
        for r in resources[:10]:
            cat = r.category
            if cat not in resource_summary:
                resource_summary[cat] = []
            resource_summary[cat].append(r.name)

        return {
            "biome": biome,
            "nearest_place": nearest.name if nearest else "Unknown",
            "lat": lat,
            "lon": lon,
            "survival": context,
            "nearby_resources": resource_summary,
        }

    def context_for_prompt(self, lat: float, lon: float) -> str:
        """
        Format location context for injection into LLM prompt.
        Used when user's location is known.
        """
        ctx = self.get_survival_context(lat, lon)
        biome = ctx["biome"]
        nearest = ctx["nearest_place"]
        survival = ctx["survival"]
        resources = ctx["nearby_resources"]

        lines = [
            f"User location context:",
            f"Biome: {biome}",
            f"Nearest known place: {nearest}",
        ]

        if survival:
            lines.append(f"Water in this biome: {survival.get('water', 'Unknown')}")
            lines.append(f"Food in this biome: {survival.get('food', 'Unknown')}")
            lines.append(f"Hazards: {survival.get('hazards', 'Unknown')}")

        if resources:
            for category, names in list(resources.items())[:3]:
                lines.append(f"Nearby {category}: {', '.join(names[:2])}")

        return "\n".join(lines)

    # ── Utility ────────────────────────────────────────────────────────────

    def _haversine(
        self, lat1: float, lon1: float,
        lat2: float, lon2: float
    ) -> float:
        """Distance between two points in km."""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat/2)**2 +
             math.cos(math.radians(lat1)) *
             math.cos(math.radians(lat2)) *
             math.sin(dlon/2)**2)
        return R * 2 * math.asin(math.sqrt(a))

    def latlon_to_pixels(
        self,
        lat: float, lon: float,
        bounds: MapBounds,
        width: int, height: int
    ) -> Tuple[int, int]:
        """Convert lat/lon to pixel coordinates within bounds."""
        x = int((lon - bounds.min_lon) /
                (bounds.max_lon - bounds.min_lon) * width)
        # Latitude is inverted (north = top)
        y = int((bounds.max_lat - lat) /
                (bounds.max_lat - bounds.min_lat) * height)
        return x, y

    def pixels_to_latlon(
        self,
        x: int, y: int,
        bounds: MapBounds,
        width: int, height: int
    ) -> Tuple[float, float]:
        """Convert pixel coordinates back to lat/lon."""
        lon = bounds.min_lon + (x / width) * (bounds.max_lon - bounds.min_lon)
        lat = bounds.max_lat - (y / height) * (bounds.max_lat - bounds.min_lat)
        return lat, lon

    def is_ready(self) -> bool:
        return self.ready

    def status(self) -> str:
        parts = []
        if self._locations_db:
            try:
                count = self._locations_db.execute(
                    "SELECT COUNT(*) FROM locations"
                ).fetchone()[0]
                parts.append(f"{count:,} locations")
            except Exception:
                parts.append("locations DB")
        if self._resources:
            parts.append(f"{len(self._resources)} resources")
        if not parts:
            return "No map data — run tools/bootstrap_map.py"
        return "Map: " + ", ".join(parts)

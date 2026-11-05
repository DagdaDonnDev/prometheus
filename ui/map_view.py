"""
Map View
========
Renders the offline world map in PySide6 using QPainter.
Pan with drag. Zoom with scroll wheel or buttons.
Tap any location for survival context.
Draws from local vector data — no internet required.
"""

import math
import json
from pathlib import Path
from typing import Optional, Tuple, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QScrollArea,
    QDialog, QTextEdit
)
from PySide6.QtCore import (
    Qt, Signal, QPoint, QRect, QRectF, QTimer, QThread
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont,
    QPixmap, QMouseEvent, QWheelEvent, QPainterPath,
    QLinearGradient
)

from core.map_engine import MapEngine, MapBounds, Location, Resource, BIOME_RULES


MAP_DIR = Path("map")

# ── Colours ────────────────────────────────────────────────────────────────

OCEAN_COLOR      = QColor("#1a3a5c")
LAND_COLOR       = QColor("#2a3a2a")
RIVER_COLOR      = QColor("#2a5a8a")
LAKE_COLOR       = QColor("#1e4a6e")
GRID_COLOR       = QColor(255, 255, 255, 25)
BORDER_COLOR     = QColor(255, 255, 255, 40)
CITY_COLOR       = QColor("#f0a500")
CITY_MAJOR_COLOR = QColor("#ffcc44")
RESOURCE_COLORS  = {
    "metal":       QColor("#b0b0c0"),
    "energy":      QColor("#c08030"),
    "agriculture": QColor("#60a040"),
    "water":       QColor("#4090c0"),
    "mineral":     QColor("#a0a040"),
    "resource":    QColor("#808060"),
}
HIGHLIGHT_COLOR  = QColor("#f0a500")
TEXT_COLOR       = QColor("#e8e8e8")
TOOLTIP_BG       = QColor(20, 20, 20, 200)

# Biome colours matching BIOME_RULES order
BIOME_COLORS = {
    "Arctic / Tundra":          QColor("#c8dce8"),
    "Boreal Forest (Taiga)":    QColor("#2a5a2a"),
    "Temperate Forest":         QColor("#3a6a3a"),
    "Mediterranean / Grassland":QColor("#8a8a40"),
    "Subtropical Desert":       QColor("#a09040"),
    "Tropical Savanna":         QColor("#607a30"),
    "Tropical Rainforest":      QColor("#1a5a1a"),
    "Subantarctic":             QColor("#6a8a8a"),
    "Antarctic":                QColor("#c8dce8"),
}


# ── Shape file renderer ────────────────────────────────────────────────────

class ShapeRenderer:
    """
    Renders Natural Earth shapefiles.
    Falls back to simplified world outline if shapefiles not available.
    """

    def __init__(self):
        self._has_shapefile = self._check_shapefile()

    def _check_shapefile(self) -> bool:
        countries = MAP_DIR / "ne_countries"
        return countries.exists() and any(countries.glob("*.shp"))

    def draw_land(
        self,
        painter: QPainter,
        bounds: MapBounds,
        width: int,
        height: int,
        engine: MapEngine
    ):
        """Draw land polygons — shapefile or simplified fallback."""
        if self._has_shapefile:
            self._draw_from_shapefile(painter, bounds, width, height)
        else:
            self._draw_simplified_continents(painter, bounds, width, height)

    def _draw_from_shapefile(self, painter, bounds, width, height):
        """Use pyshp to read and render shapefile."""
        try:
            import shapefile as sf
            shp_files = list((MAP_DIR / "ne_countries").glob("*.shp"))
            if not shp_files:
                self._draw_simplified_continents(painter, bounds, width, height)
                return

            reader = sf.Reader(str(shp_files[0]))
            painter.setBrush(QBrush(LAND_COLOR))
            painter.setPen(QPen(BORDER_COLOR, 0.5))

            for shape in reader.shapes():
                if shape.shapeType == 0:
                    continue
                self._draw_polygon(painter, shape.points, shape.parts,
                                   bounds, width, height)
        except ImportError:
            self._draw_simplified_continents(painter, bounds, width, height)

    def _draw_polygon(self, painter, points, parts, bounds, width, height):
        """Draw a polygon from shapefile points."""
        # Split into parts (outer/inner rings)
        part_starts = list(parts) + [len(points)]

        for i in range(len(parts)):
            start = part_starts[i]
            end   = part_starts[i + 1]
            ring  = points[start:end]

            if len(ring) < 3:
                continue

            path = QPainterPath()
            first = True
            for lon, lat in ring:
                # Skip points outside extended bounds
                if not (bounds.min_lon - 5 <= lon <= bounds.max_lon + 5 and
                        bounds.min_lat - 5 <= lat <= bounds.max_lat + 5):
                    if first:
                        continue
                x, y = self._to_px(lat, lon, bounds, width, height)
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)
            path.closeSubpath()
            if not first:
                painter.drawPath(path)

    def _draw_simplified_continents(self, painter, bounds, width, height):
        """
        Draw a very simplified world map when no shapefile data is available.
        Uses approximate continent outlines.
        Enough to orient the user.
        """
        painter.setBrush(QBrush(LAND_COLOR))
        painter.setPen(QPen(BORDER_COLOR, 0.5))

        # Simplified continent polygons [lon, lat]
        CONTINENTS = {
            "North America": [
                (-168, 71), (-140, 60), (-120, 49), (-95, 49), (-82, 45),
                (-70, 47), (-65, 44), (-68, 38), (-80, 25), (-90, 16),
                (-92, 8), (-78, 8), (-77, 9), (-75, 4), (-68, 12),
                (-63, 10), (-60, 15), (-62, 21), (-80, 23), (-90, 29),
                (-97, 26), (-105, 21), (-118, 16), (-105, 20), (-118, 30),
                (-125, 35), (-124, 49), (-140, 60), (-155, 60), (-168, 55),
            ],
            "South America": [
                (-80, 8), (-75, 4), (-68, 12), (-63, 10), (-60, 5),
                (-52, 4), (-50, 0), (-35, -6), (-38, -12), (-40, -19),
                (-48, -26), (-52, -33), (-58, -38), (-62, -51), (-68, -55),
                (-68, -55), (-75, -52), (-72, -42), (-70, -30), (-68, -20),
                (-70, -15), (-75, -10), (-80, -3), (-80, 8),
            ],
            "Europe": [
                (-10, 36), (0, 36), (15, 37), (28, 36), (30, 38),
                (28, 42), (30, 46), (25, 48), (30, 52), (28, 55),
                (22, 56), (18, 58), (14, 58), (10, 57), (5, 57),
                (8, 54), (5, 51), (3, 52), (0, 51), (-2, 54),
                (-5, 58), (-8, 58), (-10, 54), (-10, 50), (-8, 44),
                (-2, 43), (-5, 36), (-10, 36),
            ],
            "Africa": [
                (-18, 15), (-17, 12), (-15, 10), (-8, 5), (0, 4),
                (9, 4), (10, 2), (11, -2), (10, -8), (12, -17),
                (16, -22), (18, -29), (26, -34), (32, -30), (36, -22),
                (40, -12), (44, -8), (42, 12), (44, 12), (42, 16),
                (38, 22), (32, 30), (24, 30), (12, 32), (10, 38),
                (0, 36), (-5, 36), (-12, 28), (-18, 15),
            ],
            "Asia": [
                (26, 42), (30, 46), (36, 48), (42, 44), (50, 44),
                (60, 44), (70, 38), (72, 22), (80, 10), (90, 10),
                (100, 2), (104, 2), (108, 4), (110, 18), (120, 24),
                (122, 30), (130, 34), (140, 38), (142, 46), (140, 54),
                (134, 58), (130, 60), (120, 58), (110, 54), (100, 50),
                (90, 54), (80, 56), (70, 58), (60, 54), (50, 52),
                (40, 56), (36, 62), (30, 62), (28, 56), (26, 42),
            ],
            "Australia": [
                (114, -22), (122, -18), (130, -14), (136, -12),
                (140, -14), (142, -10), (146, -18), (150, -24),
                (154, -28), (152, -32), (150, -36), (146, -38),
                (140, -38), (134, -36), (130, -32), (118, -28),
                (114, -26), (114, -22),
            ],
            "Antarctica": [
                (-180, -70), (-120, -72), (-60, -75), (0, -72),
                (60, -70), (120, -72), (180, -70), (180, -90),
                (-180, -90),
            ],
        }

        for name, points in CONTINENTS.items():
            # Check if any point is in view
            in_view = any(
                bounds.min_lon - 20 <= lon <= bounds.max_lon + 20 and
                bounds.min_lat - 20 <= lat <= bounds.max_lat + 20
                for lon, lat in points
            )
            if not in_view:
                continue

            path = QPainterPath()
            first = True
            for lon, lat in points:
                x, y = self._to_px(lat, lon, bounds, width, height)
                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)
            path.closeSubpath()
            painter.drawPath(path)

    def _to_px(self, lat, lon, bounds, width, height) -> Tuple[int, int]:
        x = int((lon - bounds.min_lon) /
                (bounds.max_lon - bounds.min_lon) * width)
        y = int((bounds.max_lat - lat) /
                (bounds.max_lat - bounds.min_lat) * height)
        return x, y


# ── Map canvas ─────────────────────────────────────────────────────────────

class MapCanvas(QWidget):
    """
    The actual map drawing surface.
    Pan, zoom, click for info.
    """
    location_clicked = Signal(float, float)   # lat, lon
    location_hovered = Signal(float, float)   # lat, lon

    def __init__(self, engine: MapEngine, parent=None):
        super().__init__(parent)
        self.engine   = engine
        self.renderer = ShapeRenderer()

        # View state
        self._center_lat  = 30.0
        self._center_lon  = 10.0
        self._zoom        = 1.5      # degrees per 100px (lower = more zoomed in)
        self._dragging    = False
        self._drag_start  = QPoint()
        self._drag_lat    = 0.0
        self._drag_lon    = 0.0

        # Display options
        self._show_grid      = True
        self._show_resources = True
        self._show_cities    = True
        self._show_labels    = True

        # Hover tooltip
        self._hover_text = ""
        self._hover_pos  = QPoint()

        # Highlight
        self._highlight_lat: Optional[float] = None
        self._highlight_lon: Optional[float] = None

        self.setMouseTracking(True)
        self.setMinimumSize(400, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setObjectName("mapCanvas")

    # ── Rendering ──────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        bounds = self._get_bounds()

        # Ocean background
        painter.fillRect(0, 0, w, h, QBrush(OCEAN_COLOR))

        # Draw biome background bands
        self._draw_biome_bands(painter, bounds, w, h)

        # Draw land (shapefiles or simplified)
        self.renderer.draw_land(painter, bounds, w, h, self.engine)

        # Grid lines
        if self._show_grid:
            self._draw_grid(painter, bounds, w, h)

        # Rivers (if available)
        self._draw_rivers(painter, bounds, w, h)

        # Resources
        if self._show_resources and self.engine.is_ready():
            self._draw_resources(painter, bounds, w, h)

        # Cities
        if self._show_cities and self.engine.is_ready():
            self._draw_cities(painter, bounds, w, h)

        # Highlight marker
        if self._highlight_lat is not None:
            self._draw_highlight(painter, bounds, w, h)

        # Hover tooltip
        if self._hover_text:
            self._draw_tooltip(painter)

        # Scale bar
        self._draw_scale(painter, bounds, w, h)

        painter.end()

    def _get_bounds(self) -> MapBounds:
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        aspect = w / h
        lat_span = self._zoom * 100 / h * h
        lon_span = lat_span * aspect
        return MapBounds(
            min_lat=max(-90, self._center_lat - lat_span / 2),
            max_lat=min(90,  self._center_lat + lat_span / 2),
            min_lon=max(-180, self._center_lon - lon_span / 2),
            max_lon=min(180,  self._center_lon + lon_span / 2),
        )

    def _draw_biome_bands(self, painter, bounds, w, h):
        """Draw approximate biome colour bands by latitude."""
        for lat_min, lat_max, biome, _ in BIOME_RULES:
            color = BIOME_COLORS.get(biome, LAND_COLOR)
            color.setAlpha(60)
            y_top = self._lat_to_y(lat_max, bounds, h)
            y_bot = self._lat_to_y(lat_min, bounds, h)
            if y_top < h and y_bot > 0:
                painter.fillRect(
                    0, max(0, y_top), w,
                    min(h, y_bot) - max(0, y_top),
                    QBrush(color)
                )

    def _draw_grid(self, painter, bounds, w, h):
        painter.setPen(QPen(GRID_COLOR, 0.5))
        font = QFont("", 8)
        painter.setFont(font)
        painter.setPen(QPen(GRID_COLOR))

        # Latitude lines every 10 degrees
        lat = math.ceil(bounds.min_lat / 10) * 10
        while lat <= bounds.max_lat:
            y = self._lat_to_y(lat, bounds, h)
            painter.drawLine(0, y, w, y)
            if self._show_labels:
                painter.drawText(4, y - 2, f"{abs(lat)}°{'N' if lat >= 0 else 'S'}")
            lat += 10

        # Longitude lines every 10 degrees
        lon = math.ceil(bounds.min_lon / 10) * 10
        while lon <= bounds.max_lon:
            x = self._lon_to_x(lon, bounds, w)
            painter.drawLine(x, 0, x, h)
            if self._show_labels:
                label = f"{abs(lon)}°{'E' if lon >= 0 else 'W'}"
                painter.drawText(x + 2, h - 4, label)
            lon += 10

    def _draw_rivers(self, painter, bounds, w, h):
        """Draw rivers from shapefile if available."""
        rivers_dir = MAP_DIR / "ne_rivers"
        if not rivers_dir.exists():
            return
        try:
            import shapefile as sf
            shp_files = list(rivers_dir.glob("*.shp"))
            if not shp_files:
                return
            reader = sf.Reader(str(shp_files[0]))
            painter.setPen(QPen(RIVER_COLOR, 0.8))
            for shape in reader.shapes():
                if not shape.points:
                    continue
                pts = [(self._lon_to_x(lon, bounds, w),
                        self._lat_to_y(lat, bounds, h))
                       for lon, lat in shape.points
                       if (bounds.min_lon <= lon <= bounds.max_lon and
                           bounds.min_lat <= lat <= bounds.max_lat)]
                for i in range(len(pts) - 1):
                    painter.drawLine(pts[i][0], pts[i][1],
                                     pts[i+1][0], pts[i+1][1])
        except Exception:
            pass

    def _draw_resources(self, painter, bounds, w, h):
        resources = self.engine.resources_in_bounds(bounds)
        for r in resources:
            x = self._lon_to_x(r.lon, bounds, w)
            y = self._lat_to_y(r.lat, bounds, h)
            color = RESOURCE_COLORS.get(r.category, QColor("#808080"))
            painter.setBrush(QBrush(color))
            painter.setPen(QPen(color.lighter(150), 1))
            painter.drawEllipse(x - 4, y - 4, 8, 8)

            if self._show_labels and self._zoom < 3:
                painter.setPen(QPen(color.lighter(180)))
                painter.setFont(QFont("", 7))
                painter.drawText(x + 6, y + 4, r.resource_type.replace("_", " "))

    def _draw_cities(self, painter, bounds, w, h):
        # Scale minimum population with zoom level
        min_pop = max(0, int(self._zoom * 50000))
        locations = self.engine.locations_in_bounds(
            bounds, limit=100, min_population=min_pop
        )

        for loc in locations:
            x = self._lon_to_x(loc.lon, bounds, w)
            y = self._lat_to_y(loc.lat, bounds, h)

            # Size by population
            if loc.population > 1000000:
                size = 6
                color = CITY_MAJOR_COLOR
            elif loc.population > 100000:
                size = 4
                color = CITY_COLOR
            else:
                size = 2
                color = CITY_COLOR.darker(120)

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(Qt.NoPen))
            painter.drawEllipse(x - size//2, y - size//2, size, size)

            # Labels at closer zoom
            if self._show_labels and self._zoom < 2 and loc.population > 50000:
                painter.setPen(QPen(TEXT_COLOR))
                painter.setFont(QFont("", 8))
                painter.drawText(x + 4, y + 4, loc.name)

    def _draw_highlight(self, painter, bounds, w, h):
        x = self._lon_to_x(self._highlight_lon, bounds, w)
        y = self._lat_to_y(self._highlight_lat, bounds, h)

        # Pulsing cross-hair
        painter.setPen(QPen(HIGHLIGHT_COLOR, 2))
        painter.drawLine(x - 12, y, x + 12, y)
        painter.drawLine(x, y - 12, x, y + 12)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(x - 8, y - 8, 16, 16)

    def _draw_tooltip(self, painter):
        if not self._hover_text:
            return
        font = QFont("", 9)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        lines = self._hover_text.split("\n")
        line_h = metrics.height() + 2
        max_w = max(metrics.horizontalAdvance(l) for l in lines)
        pad = 8

        rx = self._hover_pos.x() + 12
        ry = self._hover_pos.y() - len(lines) * line_h - pad
        if rx + max_w + pad * 2 > self.width():
            rx = self._hover_pos.x() - max_w - pad * 2 - 12
        if ry < 0:
            ry = self._hover_pos.y() + 12

        painter.setBrush(QBrush(TOOLTIP_BG))
        painter.setPen(QPen(HIGHLIGHT_COLOR, 0.5))
        painter.drawRoundedRect(rx, ry, max_w + pad * 2,
                                len(lines) * line_h + pad, 4, 4)

        painter.setPen(QPen(TEXT_COLOR))
        for i, line in enumerate(lines):
            painter.drawText(rx + pad, ry + pad + (i + 1) * line_h - 2, line)

    def _draw_scale(self, painter, bounds, w, h):
        """Draw a scale bar in bottom right."""
        # Calculate km per pixel at centre latitude
        lat_rad = math.radians(self._center_lat)
        km_per_deg_lon = 111.32 * math.cos(lat_rad)
        lon_span = bounds.max_lon - bounds.min_lon
        km_per_pixel = (lon_span * km_per_deg_lon) / w

        # Choose a nice round number
        target_px = 80
        km = km_per_pixel * target_px
        for nice in [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000]:
            if nice >= km * 0.5:
                km = nice
                break

        bar_px = int(km / km_per_pixel)
        x = w - bar_px - 20
        y = h - 20

        painter.setPen(QPen(TEXT_COLOR, 1.5))
        painter.drawLine(x, y, x + bar_px, y)
        painter.drawLine(x, y - 3, x, y + 3)
        painter.drawLine(x + bar_px, y - 3, x + bar_px, y + 3)

        painter.setFont(QFont("", 8))
        label = f"{km:.0f}km" if km >= 1 else f"{km*1000:.0f}m"
        painter.drawText(x + bar_px // 2 - 15, y - 5, label)

    # ── Coordinate helpers ─────────────────────────────────────────────────

    def _lat_to_y(self, lat, bounds, h) -> int:
        return int((bounds.max_lat - lat) /
                   (bounds.max_lat - bounds.min_lat) * h)

    def _lon_to_x(self, lon, bounds, w) -> int:
        return int((lon - bounds.min_lon) /
                   (bounds.max_lon - bounds.min_lon) * w)

    def _px_to_latlon(self, x, y) -> Tuple[float, float]:
        bounds = self._get_bounds()
        w, h = self.width(), self.height()
        lon = bounds.min_lon + (x / w) * (bounds.max_lon - bounds.min_lon)
        lat = bounds.max_lat - (y / h) * (bounds.max_lat - bounds.min_lat)
        return lat, lon

    # ── Mouse events ───────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging  = True
            self._drag_start = event.pos()
            self._drag_lat   = self._center_lat
            self._drag_lon   = self._center_lon

    def mouseMoveEvent(self, event: QMouseEvent):
        self._hover_pos = event.pos()
        lat, lon = self._px_to_latlon(event.pos().x(), event.pos().y())

        if self._dragging:
            start_lat, start_lon = self._px_to_latlon(
                self._drag_start.x(), self._drag_start.y()
            )
            self._center_lat = max(-85, min(85,
                self._drag_lat + (start_lat - lat)
            ))
            self._center_lon = max(-180, min(180,
                self._drag_lon + (start_lon - lon)
            ))
            self.update()
        else:
            # Build hover tooltip
            biome = self.engine.get_biome(lat, lon)
            nearest = self.engine.reverse_geocode(lat, lon, radius_km=50)
            name = nearest.name if nearest else ""

            tooltip_parts = []
            if name:
                tooltip_parts.append(name)
            tooltip_parts.append(biome)
            tooltip_parts.append(
                f"{abs(lat):.1f}°{'N' if lat >= 0 else 'S'} "
                f"{abs(lon):.1f}°{'E' if lon >= 0 else 'W'}"
            )
            self._hover_text = "\n".join(tooltip_parts)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if self._dragging:
                # If barely moved — treat as click
                if (event.pos() - self._drag_start).manhattanLength() < 5:
                    lat, lon = self._px_to_latlon(
                        event.pos().x(), event.pos().y()
                    )
                    self._highlight_lat = lat
                    self._highlight_lon = lon
                    self.location_clicked.emit(lat, lon)
                self._dragging = False
                self.update()

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 0.9 if delta > 0 else 1.1
        self._zoom = max(0.2, min(60.0, self._zoom * factor))
        self.update()

    # ── Public control ─────────────────────────────────────────────────────

    def go_to(self, lat: float, lon: float, zoom: Optional[float] = None):
        self._center_lat    = lat
        self._center_lon    = lon
        self._highlight_lat = lat
        self._highlight_lon = lon
        if zoom:
            self._zoom = zoom
        self.update()

    def zoom_in(self):
        self._zoom = max(0.2, self._zoom * 0.7)
        self.update()

    def zoom_out(self):
        self._zoom = min(60.0, self._zoom * 1.4)
        self.update()

    def zoom_world(self):
        self._center_lat = 20.0
        self._center_lon = 10.0
        self._zoom = 12.0
        self.update()

    def set_show_resources(self, show: bool):
        self._show_resources = show
        self.update()

    def set_show_cities(self, show: bool):
        self._show_cities = show
        self.update()


# ── Info panel ─────────────────────────────────────────────────────────────

class LocationInfoPanel(QFrame):
    """Shows survival context when a location is clicked."""

    navigate_to_tab = Signal(str, str)  # tab_id, pre-filled query

    def __init__(self, engine: MapEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setObjectName("locationInfo")
        self.setFixedWidth(280)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._title = QLabel("Click map for info")
        self._title.setObjectName("sectionHeader")
        font = self._title.font()
        font.setBold(True)
        font.setPointSize(11)
        self._title.setFont(font)
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._biome = QLabel("")
        self._biome.setObjectName("infoValue")
        self._biome.setWordWrap(True)
        layout.addWidget(self._biome)

        self._coords = QLabel("")
        self._coords.setObjectName("infoLabel")
        layout.addWidget(self._coords)

        # Survival info sections
        for attr in ("_water_lbl", "_food_lbl", "_hazard_lbl"):
            lbl = QLabel("")
            lbl.setObjectName("infoRow")
            lbl.setWordWrap(True)
            lbl.setContentsMargins(8, 4, 8, 4)
            setattr(self, attr, lbl)
            layout.addWidget(lbl)

        # Resources nearby
        self._resources_lbl = QLabel("")
        self._resources_lbl.setObjectName("infoLabel")
        self._resources_lbl.setWordWrap(True)
        layout.addWidget(self._resources_lbl)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        survive_btn = QPushButton("🔥 Survive here")
        survive_btn.setObjectName("navBtn")
        survive_btn.clicked.connect(self._ask_survival)

        find_btn = QPushButton("📍 Find resources")
        find_btn.setObjectName("navBtn")
        find_btn.clicked.connect(self._ask_resources)

        btn_row.addWidget(survive_btn)
        btn_row.addWidget(find_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

        self._current_lat = 0.0
        self._current_lon = 0.0

    def update_location(self, lat: float, lon: float):
        self._current_lat = lat
        self._current_lon = lon

        ctx = self.engine.get_survival_context(lat, lon)
        biome = ctx["biome"]
        nearest = ctx.get("nearest_place", "Unknown")
        survival = ctx.get("survival", {})
        resources = ctx.get("nearby_resources", {})

        self._title.setText(nearest if nearest != "Unknown" else biome)
        self._biome.setText(f"🌍 {biome}")
        self._coords.setText(
            f"{abs(lat):.2f}°{'N' if lat >= 0 else 'S'}  "
            f"{abs(lon):.2f}°{'E' if lon >= 0 else 'W'}"
        )

        if survival:
            self._water_lbl.setText(f"💧 {survival.get('water', '')}")
            self._food_lbl.setText(f"🌿 {survival.get('food', '')}")
            self._hazard_lbl.setText(f"⚠ {survival.get('hazards', '')}")
        else:
            for lbl in (self._water_lbl, self._food_lbl, self._hazard_lbl):
                lbl.setText("")

        if resources:
            res_lines = []
            for cat, names in list(resources.items())[:3]:
                res_lines.append(f"• {cat}: {', '.join(names[:2])}")
            self._resources_lbl.setText("\n".join(res_lines))
        else:
            self._resources_lbl.setText("No known resources nearby")

    def _ask_survival(self):
        ctx = self.engine.get_survival_context(self._current_lat, self._current_lon)
        biome = ctx["biome"]
        nearest = ctx.get("nearest_place", "this location")
        query = (
            f"I am in a {biome} environment near {nearest}. "
            f"What are my immediate survival priorities and what "
            f"food and water sources are available here?"
        )
        self.navigate_to_tab.emit("survival", query)

    def _ask_resources(self):
        ctx = self.engine.get_survival_context(self._current_lat, self._current_lon)
        biome = ctx["biome"]
        nearest = ctx.get("nearest_place", "this location")
        query = (
            f"I am near {nearest} in a {biome} region. "
            f"What natural resources, minerals, and materials "
            f"would be available for building and survival?"
        )
        self.navigate_to_tab.emit("build", query)


# ── Full map widget ────────────────────────────────────────────────────────

class MapWidget(QWidget):
    """
    Complete map widget with canvas, controls, and info panel.
    Embeds into the main window.
    """
    navigate_to_tab = Signal(str, str)  # tab_id, query

    def __init__(self, engine: MapEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Step 1: the canvas first — the toolbar's zoom buttons connect to it
        self.canvas = MapCanvas(self.engine)
        self.canvas.location_clicked.connect(self._on_location_clicked)

        # Step 2: toolbar
        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        # Step 3: map + info panel
        content = QHBoxLayout()
        content.setSpacing(0)
        content.setContentsMargins(0, 0, 0, 0)
        content.addWidget(self.canvas)

        # Info panel
        self.info_panel = LocationInfoPanel(self.engine)
        self.info_panel.navigate_to_tab.connect(self.navigate_to_tab)
        content.addWidget(self.info_panel)

        layout.addLayout(content)

        # Status bar
        self._status = QLabel(self.engine.status())
        self._status.setObjectName("infoLabel")
        self._status.setContentsMargins(8, 2, 8, 2)
        self._status.setFixedHeight(20)
        layout.addWidget(self._status)

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("tabBar")
        bar.setFixedHeight(40)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        title = QLabel("🌍  World Map")
        title.setObjectName("sectionHeader")
        layout.addWidget(title)
        layout.addStretch()

        # Zoom controls
        zoom_in = QPushButton("+")
        zoom_in.setObjectName("smallBtn")
        zoom_in.setFixedSize(28, 28)
        zoom_in.clicked.connect(self.canvas.zoom_in)

        zoom_out = QPushButton("-")
        zoom_out.setObjectName("smallBtn")
        zoom_out.setFixedSize(28, 28)
        zoom_out.clicked.connect(self.canvas.zoom_out)

        world_btn = QPushButton("🌍")
        world_btn.setObjectName("smallBtn")
        world_btn.setFixedSize(28, 28)
        world_btn.setToolTip("Zoom to world")
        world_btn.clicked.connect(self.canvas.zoom_world)

        layout.addWidget(zoom_in)
        layout.addWidget(zoom_out)
        layout.addWidget(world_btn)

        # Search
        from PySide6.QtWidgets import QLineEdit
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search location...")
        self._search.setFixedWidth(160)
        self._search.setFixedHeight(28)
        self._search.returnPressed.connect(self._do_search)
        layout.addWidget(self._search)

        search_btn = QPushButton("🔍")
        search_btn.setObjectName("smallBtn")
        search_btn.setFixedSize(28, 28)
        search_btn.clicked.connect(self._do_search)
        layout.addWidget(search_btn)

        return bar

    def _on_location_clicked(self, lat: float, lon: float):
        self.info_panel.update_location(lat, lon)

    def _do_search(self):
        query = self._search.text().strip()
        if not query:
            return

        results = self.engine.search_locations(query, limit=1)
        if results:
            loc = results[0]
            self.canvas.go_to(loc.lat, loc.lon, zoom=2.0)
            self.info_panel.update_location(loc.lat, loc.lon)
            self._status.setText(f"Found: {loc.name}, {loc.country}")
        else:
            self._status.setText(f"Location not found: {query}")

    def go_to_location(self, lat: float, lon: float):
        """Navigate map to specific coordinates."""
        self.canvas.go_to(lat, lon, zoom=2.0)
        self.info_panel.update_location(lat, lon)

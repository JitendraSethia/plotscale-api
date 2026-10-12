"""Area and length of a single geometry, in metres."""

from dataclasses import dataclass
from enum import StrEnum

import shapely
from shapely.geometry.base import BaseGeometry

from app.services import crs

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString"}
POINT_TYPES = {"Point", "MultiPoint"}
# UTM is only defined between these latitudes.
UTM_MIN_LAT, UTM_MAX_LAT = -80, 84


class MeasurementStatus(StrEnum):
    MEASURED = "MEASURED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNSUPPORTED = "UNSUPPORTED"
    EMPTY = "EMPTY"
    INVALID = "INVALID"


@dataclass
class Measurement:
    status: MeasurementStatus
    area_m2: float | None = None
    length_m: float | None = None
    projected_crs: str | None = None
    note: str | None = None


def measure(geometry: BaseGeometry | None, source_crs: str) -> Measurement:
    """Measure a geometry in the UTM zone of its centroid. Never raises for bad geometry."""
    if geometry is None or geometry.is_empty:
        return Measurement(MeasurementStatus.EMPTY, note="Feature has no geometry.")

    geom_type = geometry.geom_type
    if geom_type in POINT_TYPES:
        return Measurement(MeasurementStatus.NOT_APPLICABLE, note="Points have no area or length.")
    if geom_type not in AREA_TYPES | LENGTH_TYPES:
        return Measurement(
            MeasurementStatus.UNSUPPORTED, note=f"Measurement is not supported for {geom_type}."
        )

    # Measure on the ground plane; KML often carries altitude values.
    geometry = shapely.force_2d(geometry)
    if not geometry.is_valid:
        return Measurement(
            MeasurementStatus.INVALID,
            note=f"Invalid geometry: {shapely.is_valid_reason(geometry)}.",
        )

    lonlat = crs.reproject(geometry, source_crs, crs.WGS84)
    min_lon, min_lat, max_lon, max_lat = lonlat.bounds
    # Catches e.g. metre coordinates in a file that claims to be EPSG:4326.
    if not (-180 <= min_lon <= max_lon <= 180 and -90 <= min_lat <= max_lat <= 90):
        return Measurement(
            MeasurementStatus.INVALID,
            note=f"Coordinates are outside the valid range for {source_crs}.",
        )

    centroid = lonlat.centroid
    if not UTM_MIN_LAT <= centroid.y <= UTM_MAX_LAT:
        return Measurement(
            MeasurementStatus.UNSUPPORTED,
            note="Feature is outside UTM coverage (80°S to 84°N).",
        )

    utm_crs = f"EPSG:{crs.utm_epsg(centroid.x, centroid.y)}"
    projected = crs.reproject(geometry, source_crs, utm_crs)
    if geom_type in AREA_TYPES:
        return Measurement(
            MeasurementStatus.MEASURED, area_m2=round(projected.area, 2), projected_crs=utm_crs
        )
    return Measurement(
        MeasurementStatus.MEASURED, length_m=round(projected.length, 2), projected_crs=utm_crs
    )

"""Choosing a projected CRS and reprojecting geometries."""

from functools import lru_cache

import shapely
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry

WGS84 = "EPSG:4326"


def utm_epsg(lon: float, lat: float) -> int:
    """EPSG code of the WGS84 UTM zone containing the point (326xx north, 327xx south)."""
    zone = min(int((lon + 180) // 6) + 1, 60)  # lon = 180 falls in zone 60, not 61
    return (32600 if lat >= 0 else 32700) + zone


def reproject(geometry: BaseGeometry, source_crs: str, target_crs: str) -> BaseGeometry:
    transformer = _transformer(source_crs, target_crs)
    # interleaved=False passes separate x and y arrays, matching Transformer.transform(xx, yy).
    return shapely.transform(geometry, transformer.transform, interleaved=False)


@lru_cache(maxsize=32)
def _transformer(source_crs: str, target_crs: str) -> Transformer:
    # always_xy keeps (lon, lat) order; EPSG:4326 officially lists latitude first.
    # Cached because building a transformer is slow and a file reuses the same few pairs.
    return Transformer.from_crs(source_crs, target_crs, always_xy=True)

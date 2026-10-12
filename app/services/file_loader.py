"""Reading features from KML and shapefiles with GDAL (via pyogrio)."""

import math
from dataclasses import dataclass
from pathlib import Path

import pyogrio
import pyogrio.raw
import shapely
from pyogrio.errors import DataLayerError, DataSourceError
from shapely.geometry.base import BaseGeometry

from app.errors import FileError


@dataclass
class LoadedFeature:
    index: int
    geometry: BaseGeometry | None
    crs: str
    properties: dict


def load_features(path: Path) -> list[LoadedFeature]:
    """Read every feature from every layer, numbering them across the whole file."""
    try:
        layer_names = [name for name, _geometry_type in pyogrio.list_layers(path)]
        features = []
        for layer in layer_names:
            features.extend(_read_layer(path, layer, start_index=len(features)))
    except (DataSourceError, DataLayerError) as exc:
        # GDAL messages include server paths, so return a generic message instead.
        raise FileError("Could not read geospatial data. The file may be corrupted.") from exc

    if not features:
        raise FileError("File contains no features.")
    return features


def _read_layer(path: Path, layer: str, start_index: int) -> list[LoadedFeature]:
    meta, _fids, geometries, field_data = pyogrio.raw.read(
        path, layer=layer, datetime_as_string=True
    )
    if meta["crs"] is None:
        raise FileError(
            "Coordinate system is unknown: the shapefile's .prj file is missing or unreadable. "
            "Include a valid .prj file so measurements can be calculated correctly."
        )

    columns = [values.tolist() for values in field_data]
    features = []
    for row, wkb in enumerate(geometries):
        properties = {
            name: _clean(column[row]) for name, column in zip(meta["fields"], columns, strict=True)
        }
        features.append(
            LoadedFeature(
                index=start_index + row,
                geometry=shapely.from_wkb(wkb) if wkb is not None else None,
                crs=meta["crs"],
                properties=properties,
            )
        )
    return features


def _clean(value):
    # Missing numeric values come back as NaN, which is not valid JSON.
    if isinstance(value, float) and math.isnan(value):
        return None
    return value

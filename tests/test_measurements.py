import pytest
from pyproj import Geod
from shapely import force_3d
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.services.measurements import MeasurementStatus, measure

GEOD = Geod(ellps="WGS84")
WGS84 = "EPSG:4326"


def geodesic_square(lon: float, lat: float, side_m: float) -> Polygon:
    """Square whose sides are exactly side_m long on the ellipsoid."""
    east = GEOD.fwd(lon, lat, 90, side_m)
    north_east = GEOD.fwd(east[0], east[1], 0, side_m)
    north = GEOD.fwd(lon, lat, 0, side_m)
    return Polygon([(lon, lat), east[:2], north_east[:2], north[:2]])


def geodesic_area(polygon) -> float:
    return abs(GEOD.geometry_area_perimeter(polygon)[0])


@pytest.mark.parametrize(
    "lon, lat, expected_crs",
    [
        (88.3639, 22.5726, "EPSG:32645"),  # Kolkata
        (151.2093, -33.8688, "EPSG:32756"),  # Sydney, southern hemisphere
    ],
)
def test_one_km_square_area(lon, lat, expected_crs):
    square = geodesic_square(lon, lat, 1000)

    result = measure(square, WGS84)

    assert result.status == MeasurementStatus.MEASURED
    assert result.projected_crs == expected_crs
    assert result.area_m2 == pytest.approx(1_000_000, rel=0.005)
    assert result.area_m2 == pytest.approx(geodesic_area(square), rel=0.005)
    assert result.length_m is None


def test_line_length_matches_geodesic():
    line = LineString([(88.3639, 22.5726), (88.373624, 22.5726), (88.373624, 22.58163)])

    result = measure(line, WGS84)

    assert result.status == MeasurementStatus.MEASURED
    assert result.length_m == pytest.approx(2000, rel=0.005)
    assert result.length_m == pytest.approx(GEOD.geometry_length(line), rel=0.005)
    assert result.area_m2 is None


def test_multipolygon_area_is_sum_of_parts():
    parts = [geodesic_square(88.42, 22.52, 200), geodesic_square(88.425, 22.52, 200)]

    whole = measure(MultiPolygon(parts), WGS84).area_m2

    assert whole == pytest.approx(sum(measure(p, WGS84).area_m2 for p in parts), abs=0.05)
    assert whole == pytest.approx(80_000, rel=0.005)


def test_multilinestring_length_is_sum_of_parts():
    parts = [LineString([(88.36, 22.57), (88.37, 22.57)]), LineString([(88.38, 22.57), (88.38, 22.58)])]

    whole = measure(MultiLineString(parts), WGS84).length_m

    assert whole == pytest.approx(sum(measure(p, WGS84).length_m for p in parts), abs=0.05)


def test_projected_source_crs_is_measured_in_metres():
    square = box(600_000, 2_500_000, 601_000, 2_501_000)  # UTM 45N, already metres

    result = measure(square, "EPSG:32645")

    assert result.area_m2 == pytest.approx(1_000_000, rel=1e-6)


def test_each_feature_uses_its_own_utm_zone():
    west = measure(geodesic_square(88.36, 22.57, 100), WGS84)  # zone 45
    east = measure(geodesic_square(90.41, 23.81, 100), WGS84)  # Dhaka, zone 46

    assert (west.projected_crs, east.projected_crs) == ("EPSG:32645", "EPSG:32646")


def test_altitude_is_ignored():
    square = geodesic_square(88.3639, 22.5726, 1000)

    assert measure(force_3d(square, 50), WGS84).area_m2 == measure(square, WGS84).area_m2


@pytest.mark.parametrize("geometry", [Point(88.36, 22.57), MultiPoint([(88.36, 22.57), (88.37, 22.58)])])
def test_points_are_not_measured(geometry):
    result = measure(geometry, WGS84)

    assert result.status == MeasurementStatus.NOT_APPLICABLE
    assert result.area_m2 is None and result.length_m is None


@pytest.mark.parametrize("geometry", [None, Polygon(), LineString()])
def test_missing_or_empty_geometry(geometry):
    assert measure(geometry, WGS84).status == MeasurementStatus.EMPTY


def test_geometry_collection_is_unsupported():
    collection = GeometryCollection([geodesic_square(88.36, 22.57, 100), Point(88.36, 22.57)])

    result = measure(collection, WGS84)

    assert result.status == MeasurementStatus.UNSUPPORTED
    assert "GeometryCollection" in result.note


def test_self_intersecting_polygon_is_invalid():
    bowtie = Polygon([(88.36, 22.57), (88.37, 22.58), (88.37, 22.57), (88.36, 22.58)])

    result = measure(bowtie, WGS84)

    assert result.status == MeasurementStatus.INVALID
    assert "Self-intersection" in result.note
    assert result.area_m2 is None


def test_coordinates_out_of_range_for_crs_are_invalid():
    # Metre values in a file that claims to be lon/lat.
    result = measure(box(600_000, 2_500_000, 601_000, 2_501_000), WGS84)

    assert result.status == MeasurementStatus.INVALID
    assert "outside the valid range" in result.note


def test_polar_feature_is_unsupported():
    result = measure(geodesic_square(10.0, 85.0, 1000), WGS84)

    assert result.status == MeasurementStatus.UNSUPPORTED
    assert "UTM coverage" in result.note

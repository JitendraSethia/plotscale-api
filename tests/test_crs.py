import pytest
from shapely.geometry import Point

from app.services.crs import WGS84, reproject, utm_epsg


@pytest.mark.parametrize(
    "lon, lat, epsg",
    [
        (88.3639, 22.5726, 32645),  # Kolkata, zone 45 north
        (151.2093, -33.8688, 32756),  # Sydney, zone 56 south
        (0.0, 0.0, 32631),  # equator counts as north
        (-180.0, 10.0, 32601),
        (180.0, 10.0, 32660),  # antimeridian stays in zone 60
    ],
)
def test_utm_epsg(lon, lat, epsg):
    assert utm_epsg(lon, lat) == epsg


def test_reproject_keeps_lon_lat_order():
    utm = reproject(Point(88.3639, 22.5726), WGS84, "EPSG:32645")
    # Kolkata is east of the zone 45 central meridian (87°E), so easting > 500 km.
    assert 600_000 < utm.x < 650_000
    assert 2_490_000 < utm.y < 2_510_000

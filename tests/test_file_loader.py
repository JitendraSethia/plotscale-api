import pytest

from app.errors import FileError
from app.services import storage
from app.services.file_loader import load_features
from tests.conftest import FIXTURES

SQUARE = "88.36,22.57 88.37,22.57 88.37,22.58 88.36,22.58 88.36,22.57"
POLYGON = (
    "<Placemark><Polygon><outerBoundaryIs><LinearRing>"
    f"<coordinates>{SQUARE}</coordinates>"
    "</LinearRing></outerBoundaryIs></Polygon></Placemark>"
)
POINT = "<Placemark><Point><coordinates>88.36,22.57</coordinates></Point></Placemark>"


def test_loads_kml_features():
    features = load_features(FIXTURES / "sample.kml")

    assert [f.index for f in features] == [0, 1, 2]
    assert [f.geometry.geom_type for f in features] == ["Polygon", "LineString", "Point"]
    assert {f.crs for f in features} == {"EPSG:4326"}
    assert features[0].properties["Name"] == "Plot A"


def test_loads_zipped_shapefile_features(tmp_path):
    shp = storage.extract_shapefile(FIXTURES / "sample_shapefile.zip", tmp_path)
    features = load_features(shp)

    assert [f.geometry.geom_type for f in features] == ["Polygon", "Polygon", "MultiPolygon"]
    assert {f.crs for f in features} == {"EPSG:4326"}
    assert features[2].properties == {"plot_no": "C-303", "name": "Plot C"}


def test_numbers_features_across_kml_folders(make_kml):
    path = make_kml(f"<Folder>{POLYGON}</Folder><Folder>{POINT}{POINT}</Folder>")
    features = load_features(path)

    assert [f.index for f in features] == [0, 1, 2]
    assert [f.geometry.geom_type for f in features] == ["Polygon", "Point", "Point"]


def test_placemark_without_geometry_has_none_geometry(make_kml):
    features = load_features(make_kml("<Placemark><name>No shape</name></Placemark>"))
    assert features[0].geometry is None


def test_shapefile_without_prj_is_rejected(tmp_path, make_zip):
    shp = storage.extract_shapefile(make_zip(drop=(".prj",)), tmp_path)
    with pytest.raises(FileError, match=r"\.prj"):
        load_features(shp)


def test_empty_kml_is_rejected(make_kml):
    with pytest.raises(FileError, match="no features"):
        load_features(make_kml(""))


def test_malformed_kml_is_rejected(tmp_path):
    path = tmp_path / "broken.kml"
    path.write_text('<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>')
    with pytest.raises(FileError, match="Could not read"):
        load_features(path)

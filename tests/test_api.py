import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select

from app import config
from app.api import files as files_api
from app.db.database import get_db
from app.db.models import File, FileStatus
from app.main import app
from tests.conftest import FIXTURES

BOWTIE = "88.36,22.57 88.37,22.58 88.37,22.57 88.36,22.58 88.36,22.57"
SQUARE = "88.36,22.57 88.37,22.57 88.37,22.58 88.36,22.58 88.36,22.57"


def kml_polygon(coordinates: str) -> str:
    return (
        "<Polygon><outerBoundaryIs><LinearRing>"
        f"<coordinates>{coordinates}</coordinates>"
        "</LinearRing></outerBoundaryIs></Polygon>"
    )


def upload(client, path: Path):
    return client.post("/api/files/", files={"file": (path.name, path.read_bytes())})


def measurements(client, file_id: str) -> dict:
    response = client.get(f"/api/files/{file_id}/measurements/")
    assert response.status_code == 200
    return response.json()


def test_upload_kml(client):
    response = upload(client, FIXTURES / "sample.kml")

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "sample.kml"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    assert body["status"] == "COMPLETED"
    assert body["error"] is None
    assert client.get(f"/api/files/{body['id']}/").json() == body


def test_kml_measurements(client):
    file_id = upload(client, FIXTURES / "sample.kml").json()["id"]

    body = measurements(client, file_id)
    plot, line, point = body["features"]

    assert body["status"] == "COMPLETED"
    assert plot["measurement_status"] == "MEASURED"
    assert plot["area_m2"] == pytest.approx(1_000_000, rel=0.005)
    assert plot["projected_crs"] == "EPSG:32645"
    assert plot["geometry"]["type"] == "Polygon"
    assert plot["crs"] == "EPSG:4326"
    assert plot["properties"]["Name"] == "Plot A"
    assert line["length_m"] == pytest.approx(2000, rel=0.005)
    assert point["measurement_status"] == "NOT_APPLICABLE"
    assert point["area_m2"] is None and point["length_m"] is None


def test_upload_zipped_shapefile(client):
    response = upload(client, FIXTURES / "sample_shapefile.zip")

    assert response.status_code == 201
    assert response.json()["feature_count"] == 3
    features = measurements(client, response.json()["id"])["features"]
    assert [f["geometry_type"] for f in features] == ["Polygon", "Polygon", "MultiPolygon"]
    assert features[2]["area_m2"] == pytest.approx(80_000, rel=0.005)
    assert features[2]["properties"] == {"plot_no": "C-303", "name": "Plot C"}


def test_invalid_content_marks_file_failed(client):
    response = upload(client, FIXTURES / "bad.kml")

    assert response.status_code == 422
    file_id = response.json()["id"]
    info = client.get(f"/api/files/{file_id}/").json()
    assert info["status"] == "FAILED"
    assert info["error"] == "File is not a valid KML document."
    assert measurements(client, file_id)["features"] == []


@pytest.mark.parametrize(
    "drop, message", [((".prj",), ".prj"), ((".dbf",), "missing required parts: .dbf")]
)
def test_incomplete_shapefile_is_rejected(client, make_zip, drop, message):
    response = upload(client, make_zip(drop=drop))

    assert response.status_code == 422
    assert message in response.json()["detail"]
    assert client.get(f"/api/files/{response.json()['id']}/").json()["status"] == "FAILED"


def test_zip_slip_is_rejected(client, make_zip):
    response = upload(client, make_zip(extra={"../../evil.txt": b"pwned"}))

    assert response.status_code == 422
    assert response.json()["detail"] == "Zip contains unsafe file paths."


def test_unsupported_extension_is_rejected(client):
    response = client.post("/api/files/", files={"file": ("notes.txt", b"hello")})

    assert response.status_code == 415


def test_empty_upload_is_rejected(client):
    response = client.post("/api/files/", files={"file": ("empty.kml", b"")})

    assert response.status_code == 400


def test_oversized_upload_is_rejected(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 1)

    response = client.post("/api/files/", files={"file": ("big.kml", b"x" * (1024 * 1024 + 1))})

    assert response.status_code == 413


def test_missing_file_field_is_rejected(client):
    assert client.post("/api/files/").status_code == 422


def test_unmeasurable_geometries_are_reported_not_crashed(client, make_kml):
    path = make_kml(
        f"<Placemark>{kml_polygon(BOWTIE)}</Placemark>"
        f"<Placemark><MultiGeometry>{kml_polygon(SQUARE)}"
        "<Point><coordinates>88.36,22.57</coordinates></Point></MultiGeometry></Placemark>"
        "<Placemark><name>No shape</name></Placemark>"
        f"<Placemark>{kml_polygon(SQUARE)}</Placemark>"
    )

    response = upload(client, path)

    assert response.status_code == 201
    features = measurements(client, response.json()["id"])["features"]
    assert [f["measurement_status"] for f in features] == [
        "INVALID",
        "UNSUPPORTED",
        "EMPTY",
        "MEASURED",
    ]
    assert "Self-intersection" in features[0]["note"]


def test_unexpected_error_marks_file_failed(client, monkeypatch):
    def broken_loader(_path):
        raise RuntimeError("boom")

    monkeypatch.setattr(files_api, "load_features", broken_loader)

    with pytest.raises(RuntimeError):
        upload(client, FIXTURES / "sample.kml")

    db = next(app.dependency_overrides[get_db]())
    record = db.scalars(select(File)).one()
    assert record.status == FileStatus.FAILED
    assert record.error == "Unexpected error while processing the file."


def test_temp_files_are_removed(client, make_zip, monkeypatch, tmp_path):
    temp_root = tmp_path / "uploads"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))

    upload(client, FIXTURES / "sample_shapefile.zip")
    upload(client, make_zip(drop=(".prj",)))

    assert list(temp_root.iterdir()) == []


def test_unknown_file_returns_404(client):
    assert client.get("/api/files/missing/").status_code == 404
    assert client.get("/api/files/missing/measurements/").status_code == 404

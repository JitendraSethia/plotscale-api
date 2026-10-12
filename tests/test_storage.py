import io

import pytest

from app import config
from app.errors import FileError
from app.services import storage
from tests.conftest import FIXTURES


@pytest.mark.parametrize(
    "filename, suffix", [("a.kml", ".kml"), ("A.KML", ".kml"), ("b.zip", ".zip")]
)
def test_validate_suffix_accepts_kml_and_zip(filename, suffix):
    assert storage.validate_suffix(filename) == suffix


@pytest.mark.parametrize("filename", ["notes.txt", "plots.shp", "", None])
def test_validate_suffix_rejects_other_types(filename):
    with pytest.raises(FileError) as exc:
        storage.validate_suffix(filename)
    assert exc.value.status_code == 415


def test_save_upload_writes_file(tmp_path):
    path = storage.save_upload(io.BytesIO(b"<kml/>"), tmp_path, ".kml")
    assert path.read_bytes() == b"<kml/>"


def test_save_upload_rejects_empty_file(tmp_path):
    with pytest.raises(FileError) as exc:
        storage.save_upload(io.BytesIO(b""), tmp_path, ".kml")
    assert exc.value.status_code == 400


def test_save_upload_rejects_oversized_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 1)
    with pytest.raises(FileError) as exc:
        storage.save_upload(io.BytesIO(b"x" * (1024 * 1024 + 1)), tmp_path, ".kml")
    assert exc.value.status_code == 413


def test_check_kml_rejects_non_kml_content():
    assert storage.check_kml(FIXTURES / "sample.kml")
    with pytest.raises(FileError, match="not a valid KML"):
        storage.check_kml(FIXTURES / "bad.kml")


def test_extract_shapefile_returns_shp_with_sidecars(tmp_path):
    shp = storage.extract_shapefile(FIXTURES / "sample_shapefile.zip", tmp_path)
    assert shp.name == "layer.shp"
    assert {p.suffix for p in shp.parent.iterdir()} == {".shp", ".shx", ".dbf", ".prj", ".cpg"}


def test_extract_shapefile_rejects_non_zip(tmp_path):
    with pytest.raises(FileError, match="not a valid zip"):
        storage.extract_shapefile(FIXTURES / "bad.kml", tmp_path)


@pytest.mark.parametrize("part", [".shx", ".dbf"])
def test_extract_shapefile_requires_all_parts(tmp_path, make_zip, part):
    with pytest.raises(FileError, match=f"missing required parts: \\{part}"):
        storage.extract_shapefile(make_zip(drop=(part,)), tmp_path)


def test_extract_shapefile_requires_exactly_one_shp(tmp_path, make_zip):
    with pytest.raises(FileError, match="exactly one .shp file, found 0"):
        storage.extract_shapefile(make_zip(drop=(".shp",)), tmp_path)
    with pytest.raises(FileError, match="exactly one .shp file, found 2"):
        storage.extract_shapefile(make_zip(extra={"other.shp": b"x"}), tmp_path)


@pytest.mark.parametrize("name", ["../evil.txt", "../../evil.shp", "/etc/evil.txt", "C:/evil.txt"])
def test_extract_shapefile_blocks_zip_slip(tmp_path, make_zip, name):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with pytest.raises(FileError, match="unsafe file paths"):
        storage.extract_shapefile(make_zip(extra={name: b"pwned"}), out_dir)
    assert not (tmp_path / "evil.txt").exists()
    assert list(out_dir.iterdir()) == []


def test_extract_shapefile_ignores_macos_metadata(tmp_path, make_zip):
    shp = storage.extract_shapefile(make_zip(extra={"__MACOSX/plots/._plots.shp": b"x"}), tmp_path)
    assert shp.exists()


def test_extract_shapefile_enforces_uncompressed_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MAX_UNZIPPED_MB", 0)
    with pytest.raises(FileError) as exc:
        storage.extract_shapefile(FIXTURES / "sample_shapefile.zip", tmp_path)
    assert exc.value.status_code == 413

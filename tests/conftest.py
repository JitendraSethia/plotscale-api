import zipfile
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def make_zip(tmp_path):
    """Build a variant of the sample shapefile zip with parts removed or extra files added."""

    def _make(drop: tuple[str, ...] = (), extra: dict[str, bytes] | None = None) -> Path:
        path = tmp_path / "variant.zip"
        with (
            zipfile.ZipFile(FIXTURES / "sample_shapefile.zip") as src,
            zipfile.ZipFile(path, "w") as dst,
        ):
            for name in src.namelist():
                if not name.endswith(drop):
                    dst.writestr(name, src.read(name))
            for name, data in (extra or {}).items():
                dst.writestr(name, data)
        return path

    return _make


@pytest.fixture
def make_kml(tmp_path):
    """Write a KML document containing the given Placemark/Folder markup."""

    def _make(body: str) -> Path:
        path = tmp_path / "test.kml"
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<kml xmlns="http://www.opengis.net/kml/2.2"><Document>{body}</Document></kml>'
        )
        return path

    return _make

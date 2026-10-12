import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base, get_db
from app.main import app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(tmp_path):
    """API client backed by a fresh SQLite database for each test."""
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    engine.dispose()


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

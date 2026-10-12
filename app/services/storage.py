"""Saving uploads to disk and unpacking shapefile archives safely."""

import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from app import config
from app.errors import FileError

ALLOWED_SUFFIXES = (".kml", ".zip")
REQUIRED_SHAPEFILE_PARTS = (".shp", ".shx", ".dbf")
OPTIONAL_SHAPEFILE_PARTS = (".prj", ".cpg")
CHUNK_SIZE = 1024 * 1024


def validate_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise FileError(
            "Unsupported file type. Upload a .kml file or a .zip containing a shapefile.",
            status_code=415,
        )
    return suffix


def save_upload(source: BinaryIO, dest_dir: Path, suffix: str) -> Path:
    """Copy the upload to disk in chunks, stopping as soon as it exceeds the size limit."""
    # Never build paths from the client's filename.
    path = dest_dir / f"upload{suffix}"
    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    with path.open("wb") as out:
        while chunk := source.read(CHUNK_SIZE):
            size += len(chunk)
            if size > limit:
                raise FileError(
                    f"File is larger than the {config.MAX_UPLOAD_MB} MB limit.", status_code=413
                )
            out.write(chunk)
    if size == 0:
        raise FileError("Uploaded file is empty.", status_code=400)
    return path


def check_kml(path: Path) -> Path:
    with path.open("rb") as f:
        head = f.read(4096).lower()
    if b"<kml" not in head:
        raise FileError("File is not a valid KML document.")
    return path


def extract_shapefile(zip_path: Path, dest_dir: Path) -> Path:
    """Extract the shapefile parts from the archive and return the path of the .shp file."""
    if not zipfile.is_zipfile(zip_path):
        raise FileError("File is not a valid zip archive.")

    with zipfile.ZipFile(zip_path) as archive:
        # macOS adds __MACOSX/._name.shp metadata files that are not real shapefiles.
        members = [
            m
            for m in archive.infolist()
            if not m.is_dir() and not m.filename.startswith("__MACOSX/")
        ]
        if any(_is_unsafe(m.filename) for m in members):
            raise FileError("Zip contains unsafe file paths.")

        shp_files = [m for m in members if _suffix(m.filename) == ".shp"]
        if len(shp_files) != 1:
            raise FileError(f"Zip must contain exactly one .shp file, found {len(shp_files)}.")

        # Sidecar files must share the .shp file's folder and base name.
        base = _base_name(shp_files[0].filename)
        parts = {
            _suffix(m.filename): m
            for m in members
            if _base_name(m.filename) == base
            and _suffix(m.filename) in REQUIRED_SHAPEFILE_PARTS + OPTIONAL_SHAPEFILE_PARTS
        }
        missing = [s for s in REQUIRED_SHAPEFILE_PARTS if s not in parts]
        if missing:
            raise FileError(f"Shapefile is missing required parts: {', '.join(missing)}.")

        if sum(m.file_size for m in parts.values()) > config.MAX_UNZIPPED_MB * 1024 * 1024:
            raise FileError(
                f"Shapefile is larger than the {config.MAX_UNZIPPED_MB} MB uncompressed limit.",
                status_code=413,
            )

        out_dir = dest_dir / "shapefile"
        out_dir.mkdir()
        # Write each part under a fixed name so nothing from the archive decides where it lands.
        for suffix, member in parts.items():
            with archive.open(member) as src, (out_dir / f"layer{suffix}").open("wb") as dst:
                shutil.copyfileobj(src, dst)

    return out_dir / "layer.shp"


def _is_unsafe(name: str) -> bool:
    """True for absolute paths or paths that climb out with '..' (zip-slip)."""
    path = PurePosixPath(name.replace("\\", "/"))
    return path.is_absolute() or ".." in path.parts or ":" in name


def _suffix(name: str) -> str:
    return PurePosixPath(name).suffix.lower()


def _base_name(name: str) -> str:
    return str(PurePosixPath(name).with_suffix("")).lower()

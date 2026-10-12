import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from shapely.geometry import mapping
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Feature, File, FileStatus
from app.errors import FileError
from app.schemas.files import FeatureMeasurement, FileInfo, FileMeasurements
from app.services import storage
from app.services.file_loader import load_features
from app.services.measurements import measure

router = APIRouter(prefix="/api/files", tags=["files"])


@router.post("/", response_model=FileInfo, status_code=201)
def upload_file(file: UploadFile, db: Session = Depends(get_db)):
    """Upload a .kml file or a zipped shapefile; its features are extracted and measured."""
    suffix = storage.validate_suffix(file.filename)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        upload_path = storage.save_upload(file.file, tmp_dir, suffix)

        record = File(filename=file.filename)
        db.add(record)
        db.commit()
        try:
            _extract_and_measure(record, upload_path, suffix, tmp_dir)
        except FileError as exc:
            _mark_failed(db, record, exc.message)
            return JSONResponse(
                status_code=exc.status_code, content={"detail": exc.message, "id": record.id}
            )
        except Exception:
            _mark_failed(db, record, "Unexpected error while processing the file.")
            raise

    db.commit()
    return record


@router.get("/{file_id}/", response_model=FileInfo)
def get_file(file_id: str, db: Session = Depends(get_db)):
    return _get_file_or_404(db, file_id)


@router.get("/{file_id}/measurements/", response_model=FileMeasurements)
def get_measurements(file_id: str, db: Session = Depends(get_db)):
    record = _get_file_or_404(db, file_id)
    return FileMeasurements(
        file_id=record.id,
        status=record.status,
        feature_count=record.feature_count,
        features=[FeatureMeasurement.model_validate(f) for f in record.features],
    )


def _extract_and_measure(record: File, upload_path: Path, suffix: str, tmp_dir: Path) -> None:
    if suffix == ".zip":
        data_path = storage.extract_shapefile(upload_path, tmp_dir)
    else:
        data_path = storage.check_kml(upload_path)
    loaded = load_features(data_path)

    for item in loaded:
        result = measure(item.geometry, item.crs)
        record.features.append(
            Feature(
                index=item.index,
                geometry_type=item.geometry.geom_type if item.geometry is not None else None,
                geometry=mapping(item.geometry) if item.geometry is not None else None,
                crs=item.crs,
                properties=item.properties,
                measurement_status=result.status,
                area_m2=result.area_m2,
                length_m=result.length_m,
                projected_crs=result.projected_crs,
                note=result.note,
            )
        )
    record.crs = loaded[0].crs
    record.feature_count = len(loaded)
    record.status = FileStatus.COMPLETED


def _mark_failed(db: Session, record: File, message: str) -> None:
    db.rollback()  # discard any features added before the failure
    record.status = FileStatus.FAILED
    record.error = message
    db.commit()


def _get_file_or_404(db: Session, file_id: str) -> File:
    record = db.get(File, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return record

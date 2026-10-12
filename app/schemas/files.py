from pydantic import BaseModel, ConfigDict

from app.db.models import FileStatus
from app.services.measurements import MeasurementStatus


class FileInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    feature_count: int
    crs: str | None
    status: FileStatus
    error: str | None = None


class FeatureMeasurement(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    index: int
    geometry_type: str | None
    measurement_status: MeasurementStatus
    area_m2: float | None
    length_m: float | None
    projected_crs: str | None
    note: str | None
    crs: str
    properties: dict
    geometry: dict | None


class FileMeasurements(BaseModel):
    file_id: str
    status: FileStatus
    feature_count: int
    features: list[FeatureMeasurement]

import uuid
from enum import StrEnum

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class FileStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uuid.uuid4().hex)
    filename: Mapped[str]
    status: Mapped[FileStatus] = mapped_column(default=FileStatus.PROCESSING)
    crs: Mapped[str | None]
    feature_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None]

    features: Mapped[list["Feature"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", order_by="Feature.index"
    )


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id"), index=True)
    index: Mapped[int]
    geometry_type: Mapped[str | None]
    geometry: Mapped[dict | None] = mapped_column(JSON)
    crs: Mapped[str]
    properties: Mapped[dict] = mapped_column(JSON)
    measurement_status: Mapped[str]
    area_m2: Mapped[float | None]
    length_m: Mapped[float | None]
    projected_crs: Mapped[str | None]
    note: Mapped[str | None]

    file: Mapped[File] = relationship(back_populates="features")

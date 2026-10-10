from typing import Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field, model_validator
from pymongo import ASCENDING, IndexModel

from app.models.base import MAX_VIDEO_SECONDS, TenantDocument
from app.models.enums import MediaKind, MediaOwnerType, MediaStatus, StorageProvider


class MediaOwnerRef(BaseModel):
    type: MediaOwnerType
    id: PydanticObjectId


class OriginalInfo(BaseModel):
    filename: Optional[str] = None
    mime: Optional[str] = None
    size_bytes: int = 0


class StorageInfo(BaseModel):
    provider: StorageProvider = StorageProvider.S3
    bucket: Optional[str] = None
    key: Optional[str] = None  # siempre prefijada: tenants/{tenant_id}/...
    url: Optional[str] = None
    thumb_key: Optional[str] = None
    thumb_url: Optional[str] = None


class ProcessedInfo(BaseModel):
    mime: Optional[str] = None
    size_bytes: int = 0
    width: Optional[int] = None
    height: Optional[int] = None
    duration_sec: Optional[float] = None
    codec: Optional[str] = None
    bitrate_kbps: Optional[int] = None


class Media(TenantDocument):
    """Imagen o video corto (máx. 15 s) procesado y comprimido en servidor."""

    owner_ref: MediaOwnerRef
    kind: MediaKind
    status: MediaStatus = MediaStatus.UPLOADED
    original: OriginalInfo = Field(default_factory=OriginalInfo)
    storage: StorageInfo = Field(default_factory=StorageInfo)
    processed: ProcessedInfo = Field(default_factory=ProcessedInfo)
    error: Optional[str] = None
    uploaded_by: Optional[PydanticObjectId] = None

    @model_validator(mode="after")
    def validate_video_duration(self):
        if self.kind == MediaKind.VIDEO:
            duration = self.processed.duration_sec
            if duration is not None and duration > MAX_VIDEO_SECONDS:
                raise ValueError(
                    f"El video no puede superar {MAX_VIDEO_SECONDS} segundos"
                )
        return self

    class Settings:
        name = "media"
        indexes = [
            IndexModel(
                [
                    ("tenant_id", ASCENDING),
                    ("owner_ref.type", ASCENDING),
                    ("owner_ref.id", ASCENDING),
                ],
                name="ix_media_tenant_owner",
            ),
            IndexModel(
                [("tenant_id", ASCENDING), ("status", ASCENDING)],
                name="ix_media_tenant_status",
            ),
        ]

from typing import List, Optional

from beanie import PydanticObjectId
from pydantic import BaseModel, Field

from app.models.enums import MediaKind, MediaOwnerType, MediaStatus
from app.models.media import MediaOwnerRef, OriginalInfo, ProcessedInfo, StorageInfo
from app.schemas.common import TimestampedOut


class MediaUploadMeta(BaseModel):
    """Campos de formulario que acompañan al archivo (multipart/form-data)."""

    owner_type: MediaOwnerType
    owner_id: PydanticObjectId
    set_as_cover: bool = False


class MediaOut(TimestampedOut):
    tenant_id: PydanticObjectId
    owner_ref: MediaOwnerRef
    kind: MediaKind
    status: MediaStatus
    original: OriginalInfo
    storage: StorageInfo
    processed: ProcessedInfo
    error: Optional[str] = None
    uploaded_by: Optional[PydanticObjectId] = None


class MediaReorderRequest(BaseModel):
    media_ids: List[PydanticObjectId] = Field(min_length=1, max_length=100)


class MediaFilter(BaseModel):
    owner_type: Optional[MediaOwnerType] = None
    owner_id: Optional[PydanticObjectId] = None
    kind: Optional[MediaKind] = None
    status: Optional[MediaStatus] = None

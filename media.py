"""Subida y gestión de multimedia (fotos y videos cortos) de propiedades y unidades.

Almacenamiento: disco local (por defecto un Volume de Railway montado en MEDIA_DIR).
Los archivos se sirven públicamente en /files/... (ver main.py) con nombres aleatorios
no adivinables; el aislamiento por tenant se garantiza en la API (todas las rutas de
escritura y listado exigen JWT de la agencia y filtran por tenant_id).

Imágenes: se validan con Pillow, se corrigen por EXIF, se reducen a 1920 px y se
comprimen a JPEG, con una miniatura de 480 px.
Videos: mp4 / webm / mov, máx. 15 s. La duración se valida con ffprobe si está
instalado en el servidor; el navegador también la valida antes de subir.
"""
import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.deps import (
    STAFF_ROLES,
    STAFF_WRITE_ROLES,
    get_current_tenant,
    require_roles,
    require_writable_tenant,
)
from app.models.base import MAX_VIDEO_SECONDS
from app.models.enums import MediaKind, MediaOwnerType, MediaStatus, StorageProvider
from app.models.media import Media, MediaOwnerRef, OriginalInfo, ProcessedInfo, StorageInfo
from app.models.property import Property
from app.models.tenant import Tenant
from app.models.unit import Unit
from app.models.user import User
from app.schemas.media import MediaOut

logger = logging.getLogger("media")

router = APIRouter(tags=["media"])

MB = 1024 * 1024
MAX_IMAGE_BYTES = settings.MAX_IMAGE_MB * MB
MAX_VIDEO_BYTES = settings.MAX_VIDEO_MB * MB
IMAGE_MAX_SIDE = 1920
THUMB_MAX_SIDE = 480


def _media_root() -> Path:
    return Path(settings.MEDIA_DIR).resolve()


# ------------------------------------------------------------------ utilidades
def _bad(detail: str, code: int = 422) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _sniff_video_ext(path: Path) -> Optional[str]:
    """Detecta el contenedor por los primeros bytes (no confía en el Content-Type)."""
    with path.open("rb") as fh:
        head = fh.read(16)
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return ".mov" if head[8:12] == b"qt  " else ".mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":  # EBML (WebM / Matroska)
        return ".webm"
    return None


def _is_probably_image(path: Path) -> bool:
    with path.open("rb") as fh:
        head = fh.read(16)
    return (
        head[:3] == b"\xff\xd8\xff"  # JPEG
        or head[:8] == b"\x89PNG\r\n\x1a\n"
        or head[:4] == b"RIFF" and head[8:12] == b"WEBP"
        or head[:6] in (b"GIF87a", b"GIF89a")
    )


def _process_image(src: Path, dest: Path, thumb: Path) -> Tuple[int, int]:
    from PIL import Image, ImageOps

    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            rgba = im.convert("RGBA")
            background = Image.new("RGB", rgba.size, (255, 255, 255))
            background.paste(rgba, mask=rgba.getchannel("A"))
            im = background
        elif im.mode != "RGB":
            im = im.convert("RGB")
        im.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE))
        im.save(dest, "JPEG", quality=82, optimize=True, progressive=True)
        width, height = im.size
        small = im.copy()
        small.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE))
        small.save(thumb, "JPEG", quality=75, optimize=True)
    return width, height


def _probe_video(path: Path) -> Optional[dict]:
    """Devuelve datos del video con ffprobe, o None si ffprobe no está instalado.

    Lanza ValueError si ffprobe existe pero no puede leer el archivo.
    """
    exe = shutil.which("ffprobe")
    if exe is None:
        return None
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            timeout=30,
            check=True,
        )
        data = json.loads(out.stdout or b"{}")
    except Exception as exc:
        raise ValueError("No se pudo leer el video") from exc
    streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    if not streams:
        raise ValueError("El archivo no contiene video")
    stream = streams[0]
    raw_duration = data.get("format", {}).get("duration") or stream.get("duration")
    try:
        duration = float(raw_duration) if raw_duration is not None else None
    except (TypeError, ValueError):
        duration = None
    bitrate = data.get("format", {}).get("bit_rate")
    return {
        "duration": duration,
        "width": stream.get("width"),
        "height": stream.get("height"),
        "codec": stream.get("codec_name"),
        "bitrate_kbps": int(int(bitrate) / 1000) if bitrate and str(bitrate).isdigit() else None,
    }


async def _save_upload(file: UploadFile, dest: Path, max_bytes: int) -> int:
    size = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise _bad(
                        "El archivo supera el tamaño máximo permitido ({} MB)".format(max_bytes // MB),
                        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    )
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise _bad("El archivo está vacío")
    return size


def _storage_path(key: str) -> Optional[Path]:
    """Ruta absoluta de un key de storage, solo si queda dentro de MEDIA_DIR."""
    root = _media_root()
    path = (root / key).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def _delete_files(media: Media) -> None:
    for key in (media.storage.key, media.storage.thumb_key):
        if not key:
            continue
        path = _storage_path(key)
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("No se pudo borrar el archivo %s", path)


async def _tenant_media_bytes(tenant_id: PydanticObjectId) -> int:
    rows = await Media.find({"tenant_id": tenant_id}).aggregate(
        [{"$group": {"_id": None, "total": {"$sum": "$processed.size_bytes"}}}]
    ).to_list()
    return int(rows[0]["total"]) if rows else 0


# ------------------------------------------------------------------- propietarios
async def _get_property(tenant: Tenant, property_id: PydanticObjectId) -> Property:
    prop = await Property.find_one({"_id": property_id, "tenant_id": tenant.id})
    if prop is None:
        raise _bad("Propiedad no encontrada", status.HTTP_404_NOT_FOUND)
    return prop


async def _get_unit(tenant: Tenant, unit_id: PydanticObjectId) -> Unit:
    unit = await Unit.find_one({"_id": unit_id, "tenant_id": tenant.id})
    if unit is None:
        raise _bad("Unidad no encontrada", status.HTTP_404_NOT_FOUND)
    return unit


async def _list_media(tenant: Tenant, owner_type: MediaOwnerType, owner_id) -> List[MediaOut]:
    docs = (
        await Media.find(
            {
                "tenant_id": tenant.id,
                "owner_ref.type": owner_type.value,
                "owner_ref.id": owner_id,
            }
        )
        .sort("created_at")
        .to_list()
    )
    return [MediaOut.model_validate(doc) for doc in docs]


# ------------------------------------------------------------------ núcleo de subida
async def _store_media(
    *,
    file: UploadFile,
    owner_type: MediaOwnerType,
    owner_id: PydanticObjectId,
    tenant: Tenant,
    user: User,
) -> Media:
    declared = (file.content_type or "").lower()
    is_video_declared = declared.startswith("video/")
    max_bytes = MAX_VIDEO_BYTES if is_video_declared else MAX_IMAGE_BYTES

    limit_bytes = (tenant.limits.max_media_mb or 0) * MB
    if limit_bytes and await _tenant_media_bytes(tenant.id) >= limit_bytes:
        raise _bad(
            "La agencia alcanzó su límite de almacenamiento ({} MB)".format(tenant.limits.max_media_mb),
            status.HTTP_403_FORBIDDEN,
        )

    key_dir = "tenants/{}".format(tenant.id)
    folder = _media_root() / key_dir
    folder.mkdir(parents=True, exist_ok=True)

    file_id = uuid.uuid4().hex
    tmp = folder / "{}.upload".format(file_id)
    original_size = await _save_upload(file, tmp, max_bytes)

    final_paths: List[Path] = []
    try:
        if _is_probably_image(tmp):
            kind = MediaKind.IMAGE
            dest = folder / "{}.jpg".format(file_id)
            thumb = folder / "{}_thumb.jpg".format(file_id)
            final_paths += [dest, thumb]
            try:
                width, height = await run_in_threadpool(_process_image, tmp, dest, thumb)
            except Exception:
                raise _bad("La imagen está dañada o su formato no es compatible")
            storage = StorageInfo(
                provider=StorageProvider.RAILWAY_VOLUME,
                key="{}/{}".format(key_dir, dest.name),
                url="/files/{}/{}".format(key_dir, dest.name),
                thumb_key="{}/{}".format(key_dir, thumb.name),
                thumb_url="/files/{}/{}".format(key_dir, thumb.name),
            )
            processed = ProcessedInfo(
                mime="image/jpeg",
                size_bytes=dest.stat().st_size,
                width=width,
                height=height,
            )
        else:
            ext = _sniff_video_ext(tmp)
            if ext is None:
                raise _bad("Formato no admitido. Usa imágenes (JPG, PNG, WebP) o videos (MP4, WebM, MOV)")
            if original_size > MAX_VIDEO_BYTES:
                raise _bad(
                    "El video supera el tamaño máximo permitido ({} MB)".format(settings.MAX_VIDEO_MB),
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
            kind = MediaKind.VIDEO
            try:
                info = await run_in_threadpool(_probe_video, tmp)
            except ValueError as exc:
                raise _bad(str(exc))
            if info and info["duration"] is not None and info["duration"] > MAX_VIDEO_SECONDS + 0.5:
                raise _bad("El video no puede superar {} segundos".format(MAX_VIDEO_SECONDS))
            dest = folder / "{}{}".format(file_id, ext)
            final_paths.append(dest)
            tmp.replace(dest)
            storage = StorageInfo(
                provider=StorageProvider.RAILWAY_VOLUME,
                key="{}/{}".format(key_dir, dest.name),
                url="/files/{}/{}".format(key_dir, dest.name),
            )
            mime = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}[ext]
            processed = ProcessedInfo(
                mime=mime,
                size_bytes=original_size,
                width=(info or {}).get("width"),
                height=(info or {}).get("height"),
                duration_sec=(info or {}).get("duration"),
                codec=(info or {}).get("codec"),
                bitrate_kbps=(info or {}).get("bitrate_kbps"),
            )

        media = Media(
            tenant_id=tenant.id,
            owner_ref=MediaOwnerRef(type=owner_type, id=owner_id),
            kind=kind,
            status=MediaStatus.READY,
            original=OriginalInfo(
                filename=(file.filename or "")[:200] or None,
                mime=declared or None,
                size_bytes=original_size,
            ),
            storage=storage,
            processed=processed,
            uploaded_by=user.id,
        )
        await media.insert()
        return media
    except Exception:
        for path in final_paths:
            path.unlink(missing_ok=True)
        raise
    finally:
        tmp.unlink(missing_ok=True)


# ----------------------------------------------------------------- propiedades
@router.post(
    "/properties/{property_id}/media",
    response_model=MediaOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_property_media(
    property_id: PydanticObjectId,
    file: UploadFile = File(...),
    set_as_cover: bool = Form(False),
    tenant: Tenant = Depends(require_writable_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    prop = await _get_property(tenant, property_id)
    media = await _store_media(
        file=file, owner_type=MediaOwnerType.PROPERTY, owner_id=prop.id, tenant=tenant, user=user
    )
    prop.media_ids.append(media.id)
    if media.kind == MediaKind.IMAGE and (set_as_cover or prop.cover_media_id is None):
        prop.cover_media_id = media.id
    await prop.save()
    return MediaOut.model_validate(media)


@router.get("/properties/{property_id}/media", response_model=List[MediaOut])
async def list_property_media(
    property_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    prop = await _get_property(tenant, property_id)
    return await _list_media(tenant, MediaOwnerType.PROPERTY, prop.id)


@router.post("/properties/{property_id}/media/{media_id}/cover", response_model=MediaOut)
async def set_property_cover(
    property_id: PydanticObjectId,
    media_id: PydanticObjectId,
    tenant: Tenant = Depends(require_writable_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    prop = await _get_property(tenant, property_id)
    media = await Media.find_one(
        {
            "_id": media_id,
            "tenant_id": tenant.id,
            "owner_ref.type": MediaOwnerType.PROPERTY.value,
            "owner_ref.id": prop.id,
        }
    )
    if media is None:
        raise _bad("Archivo no encontrado", status.HTTP_404_NOT_FOUND)
    if media.kind != MediaKind.IMAGE:
        raise _bad("Solo una imagen puede ser la portada")
    prop.cover_media_id = media.id
    await prop.save()
    return MediaOut.model_validate(media)


# -------------------------------------------------------------------- unidades
@router.post(
    "/units/{unit_id}/media",
    response_model=MediaOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_unit_media(
    unit_id: PydanticObjectId,
    file: UploadFile = File(...),
    tenant: Tenant = Depends(require_writable_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    unit = await _get_unit(tenant, unit_id)
    media = await _store_media(
        file=file, owner_type=MediaOwnerType.UNIT, owner_id=unit.id, tenant=tenant, user=user
    )
    unit.media_ids.append(media.id)
    await unit.save()
    return MediaOut.model_validate(media)


@router.get("/units/{unit_id}/media", response_model=List[MediaOut])
async def list_unit_media(
    unit_id: PydanticObjectId,
    tenant: Tenant = Depends(get_current_tenant),
    user: User = Depends(require_roles(*STAFF_ROLES)),
):
    unit = await _get_unit(tenant, unit_id)
    return await _list_media(tenant, MediaOwnerType.UNIT, unit.id)


# --------------------------------------------------------------------- borrado
@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    media_id: PydanticObjectId,
    tenant: Tenant = Depends(require_writable_tenant),
    user: User = Depends(require_roles(*STAFF_WRITE_ROLES)),
):
    media = await Media.find_one({"_id": media_id, "tenant_id": tenant.id})
    if media is None:
        raise _bad("Archivo no encontrado", status.HTTP_404_NOT_FOUND)

    owner = media.owner_ref
    if owner.type == MediaOwnerType.PROPERTY:
        prop = await Property.find_one({"_id": owner.id, "tenant_id": tenant.id})
        if prop is not None:
            prop.media_ids = [m for m in prop.media_ids if m != media.id]
            if prop.cover_media_id == media.id:
                remaining = (
                    await Media.find(
                        {
                            "tenant_id": tenant.id,
                            "_id": {"$in": prop.media_ids},
                            "kind": MediaKind.IMAGE.value,
                        }
                    )
                    .sort("created_at")
                    .limit(1)
                    .to_list()
                )
                prop.cover_media_id = remaining[0].id if remaining else None
            await prop.save()
    elif owner.type == MediaOwnerType.UNIT:
        unit = await Unit.find_one({"_id": owner.id, "tenant_id": tenant.id})
        if unit is not None:
            unit.media_ids = [m for m in unit.media_ids if m != media.id]
            if unit.floor_plan_media_id == media.id:
                unit.floor_plan_media_id = None
            await unit.save()

    await media.delete()
    _delete_files(media)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

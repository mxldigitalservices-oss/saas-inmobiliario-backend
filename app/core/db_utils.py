from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Optional

from bson.decimal128 import Decimal128
from pymongo import ReturnDocument

from app.models.tenant import Tenant


def raw_collection(model):
    """Colección cruda (Motor/PyMongo) de un documento Beanie, para operaciones atómicas."""
    getter = getattr(model, "get_motor_collection", None) or getattr(
        model, "get_pymongo_collection"
    )
    return getter()


def d128(value) -> Decimal128:
    return Decimal128(str(value))


async def next_counter(tenant_id, key: str) -> int:
    """Contador atómico por tenant (consecutivos de facturas, contratos...)."""
    collection = raw_collection(Tenant).database["counters"]
    doc = await collection.find_one_and_update(
        {"_id": "{}:{}".format(tenant_id, key)},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


def date_range_filter(
    date_from: Optional[date], date_to: Optional[date]
) -> Optional[Dict[str, Any]]:
    condition: Dict[str, Any] = {}
    if date_from:
        condition["$gte"] = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    if date_to:
        condition["$lt"] = datetime.combine(
            date_to + timedelta(days=1), time.min, tzinfo=timezone.utc
        )
    return condition or None

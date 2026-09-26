"""Airtable record → CatalogRecord. Reads allowlisted field IDs only; never raises on bad data."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pokazun.catalog import fields as f
from pokazun.search.filters import KNOWN_CONDITIONS, SEGMENT_INDEX_BY_AIRTABLE


@dataclass(frozen=True)
class CatalogRecord:
    record_id: str
    code: int
    eligible: bool
    rooms: int | None
    condition: str | None
    price_segment: int | None
    price_usd: Decimal | None
    registered_at: datetime | None
    modified_at: datetime | None
    public: dict[str, Any]


@dataclass(frozen=True)
class ParseResult:
    record_id: str
    record: CatalogRecord | None
    warnings: tuple[str, ...]


def _texts(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value.strip()}
    if isinstance(value, list):
        return {v.strip() for v in value if isinstance(v, str)}
    return set()


def _text(value: Any) -> str | None:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            return None
    return None


def _datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            d = date.fromisoformat(value)
            return datetime(d.year, d.month, d.day, tzinfo=UTC)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _scalar(value: Any) -> str | int | float | None:
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, bool):
        return None
    return value if isinstance(value, str | int | float) else None


def _photos(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {
            "id": item.get("id"),
            "url": item["url"],
            "filename": item.get("filename"),
            "width": item.get("width"),
            "height": item.get("height"),
        }
        for item in value
        if isinstance(item, dict) and isinstance(item.get("url"), str)
    ]


def is_eligible(fields: Mapping[str, Any]) -> bool:
    return all(expected in _texts(fields.get(fid)) for fid, expected in f.ELIGIBILITY.items())


def parse_record(raw: Mapping[str, Any]) -> ParseResult:
    record_id = str(raw["id"])
    fields: Mapping[str, Any] = raw.get("fields") or {}

    code = _int(fields.get(f.CODE))
    if code is None:
        return ParseResult(record_id, None, ("missing_code",))

    eligible = is_eligible(fields)
    rooms = _int(fields.get(f.ROOMS))
    if rooms is not None and rooms < 1:
        rooms = None
    condition = _text(fields.get(f.CONDITION))
    segment_text = _text(fields.get(f.PRICE_SEGMENT))
    segment = SEGMENT_INDEX_BY_AIRTABLE.get(segment_text) if segment_text else None
    price = _decimal(fields.get(f.PRICE_USD))
    registered_at = _datetime(fields.get(f.REGISTERED_AT))
    photos = _photos(fields.get(f.PHOTOS))

    warnings: list[str] = []
    if eligible:
        if rooms is None:
            warnings.append("invalid_rooms")
        if condition is None:
            warnings.append("missing_condition")
        elif condition not in KNOWN_CONDITIONS:
            warnings.append("unknown_condition")
        if segment_text is None:
            warnings.append("empty_price_segment")
        elif segment is None:
            warnings.append("unknown_price_segment")
        if price is None:
            warnings.append("missing_price")
        if registered_at is None:
            warnings.append("missing_registered_at")
        if not photos:
            warnings.append("no_photo")

    public = {
        "title": _text(fields.get(f.TITLE)),
        "description": _text(fields.get(f.DESCRIPTION)),
        "district": _text(fields.get(f.DISTRICT)),
        "street": _text(fields.get(f.STREET)),
        "floor": _scalar(fields.get(f.FLOOR)),
        "floors_total": _scalar(fields.get(f.FLOORS_TOTAL)),
        "area_m2": _scalar(fields.get(f.AREA)),
        "video_url": _text(fields.get(f.VIDEO_URL)),
        "photos": photos,
    }
    record = CatalogRecord(
        record_id=record_id,
        code=code,
        eligible=eligible,
        rooms=rooms,
        condition=condition,
        price_segment=segment,
        price_usd=price,
        registered_at=registered_at,
        modified_at=_datetime(fields.get(f.LAST_MODIFIED)),
        public=public,
    )
    return ParseResult(record_id, record, tuple(warnings))

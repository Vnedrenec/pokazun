from typing import Any

from pokazun.catalog import fields as f

OWNER_PHONE_FIELD = "fldOwnerPhoneXXXX"  # not in the allowlist: must never leak
SHOOTING_STATUS_FIELD = "fldShootingStatus"  # «Статус зйомки»: must be ignored


def raw_record(
    record_id: str = "rec001",
    code: Any = 620,
    *,
    property_type: Any = "Квартири",
    city: Any = "Чернігів",
    stage: Any = "Відзнято",
    status: Any = "Активний продаж",
    rooms: Any = 2,
    condition: Any = "Євроремонт",
    segment: Any = "41 - 55 тис.",
    price: Any = 55000,
    registered: Any = "2026-09-01",
    photos: int = 2,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    values = {
        f.CODE: code,
        f.PROPERTY_TYPE: property_type,
        f.CITY: city,
        f.STAGE: stage,
        f.STATUS: status,
        f.ROOMS: rooms,
        f.CONDITION: condition,
        f.PRICE_SEGMENT: segment,
        f.PRICE_USD: price,
        f.REGISTERED_AT: registered,
        f.DISTRICT: "Центр",
        f.STREET: "вул. П’ятницька",
        f.FLOOR: 1,
        f.FLOORS_TOTAL: 9,
        f.AREA: 68,
        f.TITLE: "2-кімнатна квартира",
        f.DESCRIPTION: "Світла квартира біля парку.",
        f.LAST_MODIFIED: "2026-09-20T10:00:00.000Z",
        f.PHOTOS: [
            {
                "id": f"att{i}",
                "url": f"https://v5.airtableusercontent.com/{record_id}/{i}.jpg",
                "filename": f"{i}.jpg",
                "width": 1280,
                "height": 960,
                "type": "image/jpeg",
            }
            for i in range(photos)
        ],
        OWNER_PHONE_FIELD: "+380671112233",
        SHOOTING_STATUS_FIELD: "Не розміщено",
    }
    values.update(extra or {})
    return {
        "id": record_id,
        "createdTime": "2026-09-01T08:00:00.000Z",
        "fields": {k: v for k, v in values.items() if v is not None},
    }

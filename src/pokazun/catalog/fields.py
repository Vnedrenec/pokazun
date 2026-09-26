"""Airtable field IDs from Д2 §4. Only these IDs are requested (fields[]) and read."""

CODE = "fldMylKHvRpyGlPyy"  # Код об'єкту — public object number
REGISTERED_AT = "fld9Fcm7SADagTobq"  # Дата реєстрації — sort key
PROPERTY_TYPE = "fldMMzu2NwGIwxGST"  # Тип_Нерухомості — eligibility
CITY = "fldPUJfWnYgeCYldL"  # Населений пункт — eligibility
DISTRICT = "fldXbiZpZGEpB4w8X"  # Район — card
STREET = "fldO5g8VzY94rnU9q"  # Вулиця — card
ROOMS = "fldjFTHg2mbioBVry"  # К-ть кімнат — filter + card
FLOOR = "fldEljxNazof4GawA"  # Поверх — card
FLOORS_TOTAL = "fldsJn1p29TDO8gpZ"  # Поверховість — card
CONDITION = "fldTjxCEHidcYjtD1"  # Стан нерухомості — filter + card
STATUS = "fldGYbuztVNjfLZUe"  # Статус — eligibility
STAGE = "fldxM11IWXSDkzptj"  # Етап — eligibility
PRICE_USD = "fldNnqL9CYwOv0g2V"  # Ціна (USD) — card + price-drop events
PRICE_SEGMENT = "fldvk07K5MGxyBNpz"  # Діапазон цін — price filter
AREA = "fldZ2CAZ7LyIOEroD"  # Загальна S (м2) — card
TITLE = "flduOsuSjp6gobDKu"  # Заголовок (для сайту)
DESCRIPTION = "fldbWvcRiP62Baccw"  # Опис (для сайту)
VIDEO_URL = "fld2wkj61Es2ilMtV"  # Відео Link
PHOTOS = "fldWVzagTDkNuzOty"  # Photo
LAST_MODIFIED = "fld90A1d5WOBrowyQ"  # Last Modified Time
# Allowlisted in Д2 §4 but not fetched until a feature needs them:
REALTOR = "fldojdt3iwj67qkUW"  # Рієлтор — service context
RECORD_ID = "fldgfV9EWXjO5Z86l"  # Record ID — duplicates API record.id

FETCH_FIELDS: tuple[str, ...] = (
    CODE,
    REGISTERED_AT,
    PROPERTY_TYPE,
    CITY,
    DISTRICT,
    STREET,
    ROOMS,
    FLOOR,
    FLOORS_TOTAL,
    CONDITION,
    STATUS,
    STAGE,
    PRICE_USD,
    PRICE_SEGMENT,
    AREA,
    TITLE,
    DESCRIPTION,
    VIDEO_URL,
    PHOTOS,
    LAST_MODIFIED,
)

ELIGIBILITY: dict[str, str] = {
    PROPERTY_TYPE: "Квартири",
    CITY: "Чернігів",
    STAGE: "Відзнято",
    STATUS: "Активний продаж",
}

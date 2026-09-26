from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pokazun.catalog import fields as f
from pokazun.catalog.record import parse_record
from tests.catalog_factory import OWNER_PHONE_FIELD, raw_record


def test_parses_eligible_record():
    result = parse_record(raw_record())
    rec = result.record
    assert result.warnings == ()
    assert rec.record_id == "rec001"
    assert rec.code == 620
    assert rec.eligible is True
    assert rec.rooms == 2
    assert rec.condition == "Євроремонт"
    assert rec.price_segment == 4
    assert rec.price_usd == Decimal("55000")
    assert rec.registered_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert rec.modified_at == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    assert rec.public["street"] == "вул. П’ятницька"
    assert rec.public["photos"][0] == {
        "id": "att0",
        "url": "https://v5.airtableusercontent.com/rec001/0.jpg",
        "filename": "0.jpg",
        "width": 1280,
        "height": 960,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("property_type", "Будинки"),
        ("city", "Київ"),
        ("stage", "Не відзнято"),
        ("status", "Продано"),
    ],
)
def test_each_eligibility_condition_required(field, value):
    assert parse_record(raw_record(**{field: value})).record.eligible is False


def test_shooting_status_is_ignored():
    rec = parse_record(raw_record()).record
    assert rec.eligible is True  # factory sets «Статус зйомки» = «Не розміщено»


def test_eligibility_accepts_list_values():
    raw = raw_record(
        property_type=["Квартири"],
        city=["Чернігів"],
        stage=["Відзнято"],
        status=["Активний продаж"],
    )
    assert parse_record(raw).record.eligible is True


def test_missing_eligibility_field_means_not_eligible():
    assert parse_record(raw_record(status=None)).record.eligible is False


def test_missing_code_skips_record():
    result = parse_record(raw_record(code=None))
    assert result.record is None
    assert result.warnings == ("missing_code",)


def test_code_as_string_and_float():
    assert parse_record(raw_record(code="621")).record.code == 621
    assert parse_record(raw_record(code=622.0)).record.code == 622


def test_private_fields_never_leak():
    raw = raw_record()
    rec = parse_record(raw).record
    assert "+380671112233" not in repr(rec)
    assert OWNER_PHONE_FIELD not in repr(rec)
    assert set(rec.public) == {
        "title",
        "description",
        "district",
        "street",
        "floor",
        "floors_total",
        "area_m2",
        "video_url",
        "photos",
    }


def test_all_price_segments_map():
    values = [
        "до 15 тис",
        "16-20 тис.",
        "21 - 30 тис.",
        "31 - 40 тис.",
        "41 - 55 тис.",
        "56 - 70 тис.",
        "71 - 100 тис.",
        "101 тис і вище",
    ]
    assert [parse_record(raw_record(segment=v)).record.price_segment for v in values] == list(
        range(8)
    )


def test_data_quality_warnings_for_eligible():
    result = parse_record(
        raw_record(
            rooms=None,
            condition="Щось нове",
            segment=None,
            price=None,
            registered=None,
            photos=0,
        )
    )
    assert result.record is not None
    assert set(result.warnings) == {
        "invalid_rooms",
        "unknown_condition",
        "empty_price_segment",
        "missing_price",
        "missing_registered_at",
        "no_photo",
    }
    assert result.record.price_segment is None


def test_unknown_segment_and_missing_condition():
    result = parse_record(raw_record(segment="200+ тис.", condition=None))
    assert set(result.warnings) == {"unknown_price_segment", "missing_condition"}


def test_no_warnings_for_ineligible_record():
    result = parse_record(raw_record(status="Продано", rooms=None, segment=None, photos=0))
    assert result.warnings == ()


def test_fetch_fields_are_exactly_the_allowlist_we_use():
    assert set(f.FETCH_FIELDS) == {
        f.CODE,
        f.REGISTERED_AT,
        f.PROPERTY_TYPE,
        f.CITY,
        f.DISTRICT,
        f.STREET,
        f.ROOMS,
        f.FLOOR,
        f.FLOORS_TOTAL,
        f.CONDITION,
        f.STATUS,
        f.STAGE,
        f.PRICE_USD,
        f.PRICE_SEGMENT,
        f.AREA,
        f.TITLE,
        f.DESCRIPTION,
        f.VIDEO_URL,
        f.PHOTOS,
        f.LAST_MODIFIED,
    }

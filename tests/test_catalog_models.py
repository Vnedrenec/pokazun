from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pokazun.db.models import ObjectState, SyncState

T0 = datetime(2026, 10, 1, tzinfo=UTC)


async def test_object_state_roundtrip(sessionmaker):
    async with sessionmaker() as s, s.begin():
        s.add(
            ObjectState(
                airtable_record_id="rec1",
                object_code=620,
                eligible=True,
                price_usd=Decimal("55000.50"),
                public={"street": "вул. П’ятницька", "photos": []},
                synced_at=T0,
            )
        )
        s.add(SyncState(source="airtable_objects"))
    async with sessionmaker() as s:
        row = await s.scalar(select(ObjectState))
        state = await s.get(SyncState, "airtable_objects")
    assert row.public["street"] == "вул. П’ятницька"
    assert row.price_usd == Decimal("55000.50")
    assert state.consecutive_failures == 0


async def test_record_id_unique(sessionmaker):
    async with sessionmaker() as s:
        s.add_all(
            [
                ObjectState(airtable_record_id="rec1", object_code=1, synced_at=T0),
                ObjectState(airtable_record_id="rec1", object_code=2, synced_at=T0),
            ]
        )
        with pytest.raises(IntegrityError):
            await s.flush()

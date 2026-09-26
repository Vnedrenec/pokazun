from datetime import UTC, datetime, timedelta, timezone

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from pokazun.catalog.airtable import AirtableClient, AirtableError, modified_after_formula

TOKEN = "patTEST1234567890.abcdefabcdefabcdefabcdef"


class FakeAirtable:
    def __init__(self) -> None:
        self.requests: list[web.Request] = []
        self.responses: list[tuple[int, dict]] = []

    async def handle(self, request: web.Request) -> web.Response:
        self.requests.append(request)
        status, body = self.responses.pop(0)
        return web.json_response(body, status=status)


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@pytest.fixture
async def airtable():
    fake = FakeAirtable()
    app = web.Application()
    app.router.add_get("/v0/{base}/{table}", fake.handle)
    async with TestServer(app) as server, aiohttp.ClientSession() as http:
        sleep = FakeSleep()
        client = AirtableClient(
            token=TOKEN,
            base_id="appBASE",
            table_id="tblTABLE",
            session=http,
            api_url=str(server.make_url("/v0")),
            sleep=sleep,
            monotonic=lambda: 1000.0,
        )
        yield fake, client, sleep


async def collect(client, **kw):
    return [r async for r in client.iter_records(fields=["fldA", "fldB"], **kw)]


async def test_paginates_with_allowlisted_fields(airtable):
    fake, client, _ = airtable
    fake.responses = [
        (200, {"records": [{"id": "rec1"}], "offset": "itr1/rec1"}),
        (200, {"records": [{"id": "rec2"}]}),
    ]
    assert [r["id"] for r in await collect(client)] == ["rec1", "rec2"]
    first, second = fake.requests
    assert first.match_info["base"] == "appBASE" and first.match_info["table"] == "tblTABLE"
    assert first.query.getall("fields[]") == ["fldA", "fldB"]
    assert first.query["returnFieldsByFieldId"] == "true"
    assert first.query["pageSize"] == "100"
    assert "filterByFormula" not in first.query
    assert first.headers["Authorization"] == f"Bearer {TOKEN}"
    assert second.query["offset"] == "itr1/rec1"


async def test_modified_after_uses_formula(airtable):
    fake, client, _ = airtable
    fake.responses = [(200, {"records": []})]
    await collect(client, modified_after=datetime(2026, 10, 1, 9, 58, tzinfo=UTC))
    assert fake.requests[0].query["filterByFormula"] == (
        "IS_AFTER(LAST_MODIFIED_TIME(), DATETIME_PARSE('2026-10-01T09:58:00.000Z'))"
    )


def test_formula_converts_to_utc():
    kyiv = timezone(timedelta(hours=3))
    formula = modified_after_formula(datetime(2026, 10, 1, 12, 0, tzinfo=kyiv))
    assert "2026-10-01T09:00:00.000Z" in formula


async def test_retries_after_rate_limit(airtable):
    fake, client, sleep = airtable
    fake.responses = [(429, {"error": "RATE_LIMIT_REACHED"}), (200, {"records": [{"id": "rec1"}]})]
    assert [r["id"] for r in await collect(client)] == ["rec1"]
    assert 30.0 in sleep.calls


async def test_retries_server_errors(airtable):
    fake, client, sleep = airtable
    fake.responses = [(502, {}), (503, {}), (200, {"records": []})]
    assert await collect(client) == []
    assert len(fake.requests) == 3
    assert 2 in sleep.calls and 4 in sleep.calls


async def test_client_error_not_retried(airtable):
    fake, client, _ = airtable
    fake.responses = [(422, {"error": {"type": "INVALID_FILTER_BY_FORMULA"}})]
    with pytest.raises(AirtableError) as err:
        await collect(client)
    assert err.value.status == 422
    assert len(fake.requests) == 1


async def test_gives_up_after_max_attempts(airtable):
    fake, client, _ = airtable
    fake.responses = [(500, {})] * 5
    with pytest.raises(AirtableError, match="gave up"):
        await collect(client)
    assert len(fake.requests) == 5


async def test_throttles_requests(airtable):
    fake, client, sleep = airtable
    fake.responses = [(200, {"records": [], "offset": "o"}), (200, {"records": []})]
    await collect(client)
    assert 0.25 in sleep.calls


async def test_token_not_in_error_message(airtable):
    fake, client, _ = airtable
    fake.responses = [(403, {"error": "INVALID_PERMISSIONS"})]
    with pytest.raises(AirtableError) as err:
        await collect(client)
    assert TOKEN not in str(err.value)

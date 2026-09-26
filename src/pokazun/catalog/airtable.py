"""Read-only Airtable REST client: list records only, allowlisted fields, throttled, retries."""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any

import aiohttp

from pokazun.log import get_logger

log = get_logger(__name__)

AIRTABLE_API_URL = "https://api.airtable.com/v0"


class AirtableError(Exception):
    def __init__(self, status: int | None, message: str) -> None:
        super().__init__(f"Airtable {status}: {message}")
        self.status = status


def modified_after_formula(ts: datetime) -> str:
    stamp = ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return f"IS_AFTER(LAST_MODIFIED_TIME(), DATETIME_PARSE('{stamp}'))"


class AirtableClient:
    def __init__(
        self,
        *,
        token: str,
        base_id: str,
        table_id: str,
        session: aiohttp.ClientSession,
        api_url: str = AIRTABLE_API_URL,
        min_interval: float = 0.25,  # Airtable allows 5 requests/s per base; stay below
        max_attempts: int = 5,
        rate_limit_pause: float = 30.0,  # Airtable asks to wait 30 s after a 429
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = f"{api_url.rstrip('/')}/{base_id}/{table_id}"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._session = session
        self._min_interval = min_interval
        self._max_attempts = max_attempts
        self._rate_limit_pause = rate_limit_pause
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request: float | None = None

    async def iter_records(
        self,
        *,
        fields: Sequence[str],
        modified_after: datetime | None = None,
        page_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        base_params: list[tuple[str, str]] = [
            ("pageSize", str(page_size)),
            ("returnFieldsByFieldId", "true"),
            *(("fields[]", field) for field in fields),
        ]
        if modified_after is not None:
            base_params.append(("filterByFormula", modified_after_formula(modified_after)))
        offset: str | None = None
        while True:
            params = base_params + ([("offset", offset)] if offset else [])
            page = await self._get(params)
            for record in page.get("records", []):
                yield record
            offset = page.get("offset")
            if not offset:
                return

    async def _throttle(self) -> None:
        if self._last_request is not None:
            wait = self._last_request + self._min_interval - self._monotonic()
            if wait > 0:
                await self._sleep(wait)
        self._last_request = self._monotonic()

    async def _get(self, params: list[tuple[str, str]]) -> dict[str, Any]:
        last_error = "no attempts made"
        for attempt in range(1, self._max_attempts + 1):
            await self._throttle()
            try:
                async with self._session.get(
                    self._url, params=params, headers=self._headers
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    body = (await resp.text())[:300]
                    if resp.status == 429:
                        last_error = "HTTP 429 rate limited"
                        log.warning("airtable_rate_limited", attempt=attempt)
                        await self._sleep(self._rate_limit_pause)
                        continue
                    if resp.status < 500:
                        raise AirtableError(resp.status, body)
                    last_error = f"HTTP {resp.status}: {body}"
            except (aiohttp.ClientError, TimeoutError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            log.warning("airtable_retry", attempt=attempt, error=last_error)
            await self._sleep(min(2**attempt, 30))
        raise AirtableError(None, f"gave up after {self._max_attempts} attempts: {last_error}")

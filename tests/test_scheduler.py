import asyncio
from datetime import timedelta

from aiogram.methods import SendMessage

from pokazun.alerts import AlertService
from pokazun.worker.scheduler import Job, Scheduler
from tests.tg import make_bot


async def test_failure_alerts_and_loop_continues():
    bot, session = make_bot()
    scheduler = Scheduler(AlertService(bot, -1, "prod"))
    runs = 0
    stop = asyncio.Event()

    async def flaky() -> None:
        nonlocal runs
        runs += 1
        if runs >= 3:
            stop.set()
        raise ValueError("nope")

    scheduler.add(Job("flaky", timedelta(milliseconds=5), flaky))
    await asyncio.wait_for(scheduler.run(stop), timeout=2)
    assert runs == 3
    [alert] = session.sent(SendMessage)  # debounced: one alert per error kind
    assert "flaky" in alert.text and "ValueError" in alert.text


async def test_alert_on_failure_disabled():
    bot, session = make_bot()
    scheduler = Scheduler(AlertService(bot, -1, "prod"))

    async def fails() -> None:
        raise ValueError("handled by the job itself")

    ok = await scheduler.run_once(Job("sync", timedelta(minutes=5), fails, alert_on_failure=False))
    assert ok is False
    assert session.requests == []


async def test_run_on_start_false_waits_first_interval():
    scheduler = Scheduler(AlertService(None, None, "dev"))
    calls = 0
    stop = asyncio.Event()

    async def job() -> None:
        nonlocal calls
        calls += 1

    scheduler.add(Job("late", timedelta(seconds=10), job, run_on_start=False))
    task = asyncio.create_task(scheduler.run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert calls == 0

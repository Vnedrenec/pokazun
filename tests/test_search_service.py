from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from pokazun.db.models import Search, SearchDraft, SubscriptionState, User
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption
from pokazun.search.service import (
    DraftError,
    advance,
    close_edit_menu,
    confirm_draft,
    discard_draft,
    get_active_search,
    get_draft,
    open_edit_menu,
    open_filter,
    set_conditions,
    set_price,
    set_rooms,
    start_edit,
    start_or_resume,
    view,
)
from pokazun.search.steps import DraftMode, Step
from pokazun.users.repository import touch_user

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(days=3)


@pytest.fixture
async def user_id(sessionmaker) -> int:
    async with sessionmaker() as s, s.begin():
        return (await touch_user(s, telegram_user_id=1, username=None, first_name=None, now=T0)).id


async def fill_and_confirm(sessionmaker, user_id, now=T0):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        set_rooms(draft, frozenset({RoomOption.TWO}))
        assert advance(draft)
        set_conditions(draft, frozenset({ConditionGroup.RESIDENTIAL}))
        assert advance(draft)
        set_price(draft, PriceRange(2, 4))
        assert advance(draft)
        assert draft.step is Step.SUMMARY
        user = await s.get(User, user_id)
        return await confirm_draft(s, user, now)


async def test_new_draft_and_resume(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        assert (draft.mode, draft.step) == (DraftMode.CREATE, Step.ROOMS)
        set_rooms(draft, frozenset({RoomOption.ONE, RoomOption.FOUR_PLUS}))
        assert advance(draft)
    async with sessionmaker() as s, s.begin():
        resumed = await start_or_resume(s, user_id)
        v = view(resumed)
    assert v.step is Step.CONDITION
    assert v.rooms == {RoomOption.ONE, RoomOption.FOUR_PLUS}


async def test_advance_requires_selection(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        assert advance(draft) is False
        assert draft.step is Step.ROOMS


async def test_after_summary_filters_return_to_edit_menu(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        set_rooms(draft, frozenset({RoomOption.TWO}))
        advance(draft)
        set_conditions(draft, frozenset({ConditionGroup.DEVELOPER}))
        advance(draft)
        set_price(draft, PriceRange(0, 1))
        advance(draft)
        assert draft.step is Step.SUMMARY and draft.reached_summary
        assert open_edit_menu(draft) and draft.step is Step.EDIT_MENU
        assert open_filter(draft, Step.ROOMS) and draft.step is Step.ROOMS
        set_rooms(draft, frozenset({RoomOption.THREE}))
        assert advance(draft) and draft.step is Step.EDIT_MENU
        assert close_edit_menu(draft) and draft.step is Step.SUMMARY


async def test_invalid_transitions_rejected(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        assert open_edit_menu(draft) is False
        assert open_filter(draft, Step.PRICE) is False
        assert close_edit_menu(draft) is False
        with pytest.raises(DraftError):
            await confirm_draft(s, await s.get(User, user_id), T0)


async def test_confirm_creates_search_with_baseline(sessionmaker, user_id):
    result = await fill_and_confirm(sessionmaker, user_id)
    assert result.created is True
    async with sessionmaker() as s:
        search = await get_active_search(s, user_id)
        user = await s.get(User, user_id)
        assert await get_draft(s, user_id) is None
    assert search.baseline_at == T0 and search.confirmed_at == T0
    assert search.criteria.price == PriceRange(2, 4)
    assert user.subscription_state is SubscriptionState.ACTIVE


async def test_confirm_first_search_reactivates_paused_user(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        (await s.get(User, user_id)).subscription_state = SubscriptionState.PAUSED_BY_USER
    result = await fill_and_confirm(sessionmaker, user_id)
    assert result.created is True
    async with sessionmaker() as s:
        user = await s.get(User, user_id)
        search = await get_active_search(s, user_id)
    assert user.subscription_state is SubscriptionState.ACTIVE
    assert search is not None and search.baseline_at == T0


async def test_confirm_without_draft_returns_none(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        assert await confirm_draft(s, await s.get(User, user_id), T0) is None


async def test_find_with_active_search_opens_edit(sessionmaker, user_id):
    await fill_and_confirm(sessionmaker, user_id)
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        v = view(draft)
    assert (v.mode, v.step, v.reached_summary) == (DraftMode.EDIT, Step.EDIT_MENU, True)
    assert v.price == PriceRange(2, 4) and v.rooms == {RoomOption.TWO}


async def test_edit_draft_does_not_touch_active_search(sessionmaker, user_id):
    await fill_and_confirm(sessionmaker, user_id)
    async with sessionmaker() as s, s.begin():
        draft = await start_edit(s, user_id)
        open_filter(draft, Step.PRICE)
        set_price(draft, PriceRange(6, 7))
    async with sessionmaker() as s:
        search = await get_active_search(s, user_id)
    assert search.criteria.price == PriceRange(2, 4)
    assert search.baseline_at == T0


async def test_confirm_edit_replaces_atomically_and_rebaselines(sessionmaker, user_id):
    await fill_and_confirm(sessionmaker, user_id)
    async with sessionmaker() as s, s.begin():
        user = await s.get(User, user_id)
        user.subscription_state = SubscriptionState.PAUSED_BY_USER
    async with sessionmaker() as s, s.begin():
        draft = await start_edit(s, user_id)
        open_filter(draft, Step.PRICE)
        set_price(draft, PriceRange(6, 7))
        advance(draft)
        result = await confirm_draft(s, await s.get(User, user_id), T1)
    assert result.created is False
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(Search)) == 1
        search = await get_active_search(s, user_id)
        user = await s.get(User, user_id)
    assert search.criteria.price == PriceRange(6, 7)
    assert search.baseline_at == T1
    assert user.subscription_state is SubscriptionState.PAUSED_BY_USER


async def test_edit_mode_confirm_only_from_edit_menu(sessionmaker, user_id):
    await fill_and_confirm(sessionmaker, user_id)
    async with sessionmaker() as s, s.begin():
        draft = await start_edit(s, user_id)
        open_filter(draft, Step.ROOMS)
        with pytest.raises(DraftError):
            await confirm_draft(s, await s.get(User, user_id), T1)


async def test_discard(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        draft = await start_or_resume(s, user_id)
        await discard_draft(s, draft)
    async with sessionmaker() as s:
        assert await s.scalar(select(func.count()).select_from(SearchDraft)) == 0


async def test_start_edit_without_search_fails(sessionmaker, user_id):
    async with sessionmaker() as s, s.begin():
        with pytest.raises(DraftError):
            await start_edit(s, user_id)

"""Search draft lifecycle and confirmation (Д1 §3.4, §4; Д2 §6, §7, §23).

No Telegram dependencies.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pokazun.db.models import Search, SearchDraft, SubscriptionState, User
from pokazun.search.filters import ConditionGroup, PriceRange, RoomOption, SearchCriteria
from pokazun.search.steps import FILTER_STEPS, DraftMode, Step

_NEXT_STEP = {Step.ROOMS: Step.CONDITION, Step.CONDITION: Step.PRICE, Step.PRICE: Step.SUMMARY}


class DraftError(Exception):
    pass


@dataclass(frozen=True)
class DraftView:
    mode: DraftMode
    step: Step
    rooms: frozenset[RoomOption]
    conditions: frozenset[ConditionGroup]
    price: PriceRange | None
    reached_summary: bool

    @property
    def criteria(self) -> SearchCriteria | None:
        if not self.rooms or not self.conditions or self.price is None:
            return None
        return SearchCriteria(self.rooms, self.conditions, self.price)


@dataclass(frozen=True)
class ConfirmResult:
    search: Search
    created: bool


def view(draft: SearchDraft) -> DraftView:
    price = (
        PriceRange(draft.price_low, draft.price_high)
        if draft.price_low is not None and draft.price_high is not None
        else None
    )
    return DraftView(
        mode=draft.mode,
        step=draft.step,
        rooms=frozenset(RoomOption(r) for r in draft.rooms),
        conditions=frozenset(ConditionGroup(c) for c in draft.conditions),
        price=price,
        reached_summary=draft.reached_summary,
    )


async def get_active_search(
    session: AsyncSession, user_id: int, *, for_update: bool = False
) -> Search | None:
    stmt = select(Search).where(Search.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def get_draft(
    session: AsyncSession, user_id: int, *, for_update: bool = False
) -> SearchDraft | None:
    return await session.get(SearchDraft, user_id, with_for_update=for_update)


def set_rooms(draft: SearchDraft, rooms: frozenset[RoomOption]) -> None:
    draft.rooms = sorted(r.value for r in rooms)


def set_conditions(draft: SearchDraft, conditions: frozenset[ConditionGroup]) -> None:
    draft.conditions = sorted(c.value for c in conditions)


def set_price(draft: SearchDraft, price: PriceRange | None) -> None:
    draft.price_low = price.low if price else None
    draft.price_high = price.high if price else None


def _fill(
    draft: SearchDraft,
    *,
    mode: DraftMode,
    step: Step,
    rooms: frozenset[RoomOption],
    conditions: frozenset[ConditionGroup],
    price: PriceRange | None,
    reached_summary: bool,
) -> None:
    draft.mode = mode
    draft.step = step
    set_rooms(draft, rooms)
    set_conditions(draft, conditions)
    set_price(draft, price)
    draft.reached_summary = reached_summary


async def start_or_resume(session: AsyncSession, user_id: int) -> SearchDraft:
    draft = await get_draft(session, user_id, for_update=True)
    if draft is not None:
        return draft
    if await get_active_search(session, user_id) is not None:
        return await start_edit(session, user_id)
    draft = SearchDraft(user_id=user_id)
    _fill(
        draft,
        mode=DraftMode.CREATE,
        step=Step.ROOMS,
        rooms=frozenset(),
        conditions=frozenset(),
        price=None,
        reached_summary=False,
    )
    session.add(draft)
    await session.flush()
    return draft


async def start_edit(session: AsyncSession, user_id: int) -> SearchDraft:
    search = await get_active_search(session, user_id)
    if search is None:
        raise DraftError("no active search to edit")
    criteria = search.criteria
    draft = await get_draft(session, user_id, for_update=True)
    if draft is None:
        draft = SearchDraft(user_id=user_id)
        session.add(draft)
    _fill(
        draft,
        mode=DraftMode.EDIT,
        step=Step.EDIT_MENU,
        rooms=criteria.rooms,
        conditions=criteria.conditions,
        price=criteria.price,
        reached_summary=True,
    )
    await session.flush()
    return draft


def advance(draft: SearchDraft) -> bool:
    current = view(draft)
    filled = {
        Step.ROOMS: bool(current.rooms),
        Step.CONDITION: bool(current.conditions),
        Step.PRICE: current.price is not None,
    }
    if not filled.get(draft.step, False):
        return False
    if draft.reached_summary:
        draft.step = Step.EDIT_MENU
        return True
    draft.step = _NEXT_STEP[draft.step]
    if draft.step is Step.SUMMARY:
        draft.reached_summary = True
    return True


def open_edit_menu(draft: SearchDraft) -> bool:
    if draft.step is not Step.SUMMARY:
        return False
    draft.step = Step.EDIT_MENU
    return True


def open_filter(draft: SearchDraft, step: Step) -> bool:
    if draft.step is not Step.EDIT_MENU or step not in FILTER_STEPS:
        return False
    draft.step = step
    return True


def close_edit_menu(draft: SearchDraft) -> bool:
    if draft.step is not Step.EDIT_MENU or draft.mode is not DraftMode.CREATE:
        return False
    draft.step = Step.SUMMARY
    return True


async def discard_draft(session: AsyncSession, draft: SearchDraft) -> None:
    await session.delete(draft)
    await session.flush()


async def confirm_draft(session: AsyncSession, user: User, now: datetime) -> ConfirmResult | None:
    """Atomically turns the draft into the active search and sets a new baseline (Д2 §23)."""
    draft = await get_draft(session, user.id, for_update=True)
    if draft is None:
        return None
    expected = Step.SUMMARY if draft.mode is DraftMode.CREATE else Step.EDIT_MENU
    if draft.step is not expected:
        raise DraftError(f"cannot confirm a {draft.mode} draft at step {draft.step}")
    criteria = view(draft).criteria
    if criteria is None:
        raise DraftError("draft is incomplete")

    search = await get_active_search(session, user.id, for_update=True)
    created = search is None
    if search is None:
        search = Search(user_id=user.id)
        session.add(search)
        user.subscription_state = SubscriptionState.ACTIVE
    search.rooms = sorted(r.value for r in criteria.rooms)
    search.conditions = sorted(c.value for c in criteria.conditions)
    search.price_low = criteria.price.low
    search.price_high = criteria.price.high
    search.baseline_at = now
    search.confirmed_at = now
    await session.delete(draft)
    await session.flush()
    return ConfirmResult(search=search, created=created)

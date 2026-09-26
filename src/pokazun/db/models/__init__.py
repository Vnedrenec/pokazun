"""Importing this package registers every model on Base.metadata (used by Alembic and tests)."""

from pokazun.db.models.catalog import ObjectState, SyncState
from pokazun.db.models.search import Search, SearchDraft
from pokazun.db.models.system import ProcessedUpdate
from pokazun.db.models.users import DeliveryState, SubscriptionState, User

__all__ = [
    "DeliveryState",
    "ObjectState",
    "ProcessedUpdate",
    "Search",
    "SearchDraft",
    "SubscriptionState",
    "SyncState",
    "User",
]

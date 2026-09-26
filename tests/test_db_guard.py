import pytest
from _pytest.outcomes import Failed

import tests.conftest as conftest


def test_guard_rejects_same_db_implicit_vs_explicit_port(monkeypatch):
    monkeypatch.setattr(
        conftest,
        "_ORIGINAL_DATABASE_URL",
        "postgresql+asyncpg://pokazun:pokazun@127.0.0.1/pokazun_test_agent_ws",
    )
    with pytest.raises(Failed):
        conftest._guard_database_url(
            "postgresql+asyncpg://pokazun:pokazun@127.0.0.1:5432/pokazun_test_agent_ws"
        )


def test_guard_rejects_same_db_explicit_vs_implicit_port(monkeypatch):
    monkeypatch.setattr(
        conftest,
        "_ORIGINAL_DATABASE_URL",
        "postgresql+asyncpg://pokazun:pokazun@127.0.0.1:5432/pokazun_test_agent_ws",
    )
    with pytest.raises(Failed):
        conftest._guard_database_url(
            "postgresql+asyncpg://pokazun:pokazun@127.0.0.1/pokazun_test_agent_ws"
        )


def test_guard_allows_real_differences(monkeypatch):
    monkeypatch.setattr(
        conftest,
        "_ORIGINAL_DATABASE_URL",
        "postgresql+asyncpg://pokazun:pokazun@127.0.0.1:5432/pokazun_test_agent_ws",
    )
    other_port = "postgresql+asyncpg://pokazun:pokazun@127.0.0.1:5433/pokazun_test_agent_ws"
    assert conftest._guard_database_url(other_port) == other_port
    other_host = "postgresql+asyncpg://pokazun:pokazun@127.0.0.2:5432/pokazun_test_agent_ws"
    assert conftest._guard_database_url(other_host) == other_host
    other_db = "postgresql+asyncpg://pokazun:pokazun@127.0.0.1:5432/pokazun_test_agent_other"
    assert conftest._guard_database_url(other_db) == other_db

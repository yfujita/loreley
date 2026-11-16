"""`sources` のテストの共通部品。"""

from typing import Any

from loreley_crawler.common.retry import Retrier, RetryPolicy
from loreley_crawler.connectors.registry import ConnectorRegistry
from loreley_crawler.sources import NewSource, SourceSettingsInput, SourceStore
from tests.fakes.clock import FixedClock
from tests.fakes.fake_connector import FakeConnectorType
from tests.fakes.in_memory_repository import InMemoryRepository

CONNECTOR_TYPE = "file_system"
SECRET_REFERENCE = "SECRET-credential-reference"

# 待たずに、決定的にリトライする(試行 3 回)。
NO_WAIT_RETRIER = Retrier(
    RetryPolicy(3, 0.0, 1.0, 0.0, 0.0), sleep=lambda _seconds: None, wait_slice_seconds=1_000
)


def make_registry(connector_type: FakeConnectorType | None = None) -> ConnectorRegistry:
    return ConnectorRegistry({CONNECTOR_TYPE: connector_type or FakeConnectorType()})


def make_settings(**overrides: Any) -> SourceSettingsInput:
    values: dict[str, Any] = {
        "connector_config": {"root": "/data", "token": SECRET_REFERENCE},
        "ttl": 2_592_000,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
    }
    values.update(overrides)
    return SourceSettingsInput(**values)


def make_new_source(source_id: str = "docs", **overrides: Any) -> NewSource:
    return NewSource(source_id, CONNECTOR_TYPE, make_settings(**overrides))


def make_store(
    repository: InMemoryRepository, clock: FixedClock, *, max_conflict_attempts: int = 5
) -> SourceStore:
    return SourceStore(
        repository, clock, NO_WAIT_RETRIER, max_conflict_attempts=max_conflict_attempts
    )

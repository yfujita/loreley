"""メンテナンスフラグは fail-closed で読む(architecture 7.9。テスト観点 #18 の読み取り部分)。"""

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.jobs.records import MAINTENANCE_RECORD_ID, is_maintenance_enabled
from tests.fakes import in_memory_repository as ops
from tests.fakes.in_memory_repository import InMemoryRepository


def test_the_flag_is_not_set_when_there_is_no_document() -> None:
    assert is_maintenance_enabled(InMemoryRepository()) is False


def test_the_flag_is_not_set_only_when_enabled_is_the_boolean_false() -> None:
    repository = InMemoryRepository()
    repository.seed(MAINTENANCE_RECORD_ID, {"enabled": False})

    assert is_maintenance_enabled(repository) is False


def test_the_flag_is_set_when_enabled_is_true() -> None:
    repository = InMemoryRepository()
    repository.seed(MAINTENANCE_RECORD_ID, {"enabled": True})

    assert is_maintenance_enabled(repository) is True


@pytest.mark.parametrize(
    "body",
    [
        {},  # 項目の欠落
        {"enabled": None},
        {"enabled": "false"},  # 真偽値でない
        {"enabled": "true"},
        {"enabled": 0},  # 0 は False ではない
        {"enabled": 1},
        {"enabled": ""},
        {"enabled": []},
        {"enabled": {}},
        {"enabled": "False"},
        {"other": False},
    ],
)
def test_a_malformed_flag_counts_as_set(body: dict[str, object]) -> None:
    repository = InMemoryRepository()
    repository.seed(MAINTENANCE_RECORD_ID, body)

    assert is_maintenance_enabled(repository) is True


def test_the_flag_is_read_by_its_fixed_id_with_one_read() -> None:
    repository = InMemoryRepository()
    repository.seed(MAINTENANCE_RECORD_ID, {"enabled": False})
    repository.seed("not-maintenance", {"enabled": True})

    is_maintenance_enabled(repository)

    assert [call.key for call in repository.behavior.calls_of(ops.FETCH)] == ["maintenance"]


def test_a_store_failure_is_not_turned_into_a_flag_value() -> None:
    repository = InMemoryRepository()
    repository.behavior.inject(ops.FETCH, StoreUnavailableError("timeout"))

    with pytest.raises(StoreUnavailableError):
        is_maintenance_enabled(repository)

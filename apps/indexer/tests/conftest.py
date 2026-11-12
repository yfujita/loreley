import logging
from collections.abc import Iterator

import pytest

from loreley_indexer.common.log_setup import RESTRICTED_LOGGER_NAMES
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.llm import FakeLlmClient


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def search_index() -> InMemorySearchIndex:
    return InMemorySearchIndex()


@pytest.fixture
def deletions_store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def jobs_store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def llm() -> FakeLlmClient:
    return FakeLlmClient()


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """ルートと制限対象ロガーの設定を戻す(`configure_logging` を呼ぶテストの後始末)。"""
    names = ["", *RESTRICTED_LOGGER_NAMES]
    saved = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).level) for name in names
    }
    yield
    for name, (handlers, level) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)

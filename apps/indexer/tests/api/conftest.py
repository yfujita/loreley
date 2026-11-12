from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_indexer.config import Settings
from loreley_indexer.main import Backends, build_application
from tests.api.factories import make_settings
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_search_index import InMemorySearchIndex
from tests.fakes.in_memory_store import InMemoryStore
from tests.fakes.llm import FakeLlmClient


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def backends(
    search_index: InMemorySearchIndex,
    deletions_store: InMemoryStore,
    jobs_store: InMemoryStore,
    llm: FakeLlmClient,
) -> Backends:
    return Backends(
        search_index=search_index, deletions_store=deletions_store, jobs_store=jobs_store, llm=llm
    )


@pytest.fixture
def app(settings: Settings, backends: Backends, clock: FixedClock) -> FastAPI:
    return build_application(settings, backends, clock=clock)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """lifespan(起動時の整理とワーカーの起動・停止)込み。想定外の例外はサーバ側で 500 にする。"""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

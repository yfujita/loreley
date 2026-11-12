"""検証・エラー写像のテスト用の、ドメインの代役。呼ばれたかどうかを記録する。"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_indexer.api import ApiConfig, ApiDependencies, create_api_app
from tests.api.factories import (
    MAX_BATCH_BYTES,
    MAX_BATCH_DOCUMENTS,
    MAX_LAST_SEEN_IDS,
    MAX_RAW_BYTES,
    MAX_REQUEST_BODY_BYTES,
)


def make_api_config(**overrides: int) -> ApiConfig:
    values = {
        "max_request_body_bytes": MAX_REQUEST_BODY_BYTES,
        "max_batch_documents": MAX_BATCH_DOCUMENTS,
        "max_batch_bytes": MAX_BATCH_BYTES,
        "max_raw_bytes": MAX_RAW_BYTES,
        "max_last_seen_ids": MAX_LAST_SEEN_IDS,
    }
    return ApiConfig(**{**values, **overrides})


class StubDependencies:
    """4 つの入口の代役(`MagicMock`)。検証に落ちたリクエストは、どれも呼ばない。"""

    def __init__(self) -> None:
        self.crawl_runs = MagicMock(name="crawl_runs")
        self.deletion = MagicMock(name="deletion")
        self.registrar = MagicMock(name="registrar")
        self.last_seen = MagicMock(name="last_seen")
        self.registrar.register.return_value = []
        self.last_seen.update.return_value = []
        self.deletion.discard_source_crawls.return_value = []
        self.deletion.delete_source_documents.return_value = 0
        self.deletion.delete_source_records.return_value = True

    def as_dependencies(self) -> ApiDependencies:
        return ApiDependencies(
            crawl_runs=self.crawl_runs,
            deletion=self.deletion,
            registrar=self.registrar,
            last_seen=self.last_seen,
        )

    def calls(self) -> list[str]:
        """どの入口のどのメソッドが呼ばれたか(`crawl_runs.start_crawl` の形)。"""
        names = ("crawl_runs", "deletion", "registrar", "last_seen")
        return [f"{name}.{call[0]}" for name in names for call in getattr(self, name).method_calls]


def make_stub_app(
    stubs: StubDependencies, config: ApiConfig | None = None, *, ready: bool = True
) -> FastAPI:
    ready_event = threading.Event()
    if ready:
        ready_event.set()
    return create_api_app(
        dependencies=stubs.as_dependencies(),
        config=config if config is not None else make_api_config(),
        ready=ready_event,
    )


@contextmanager
def stub_client(
    stubs: StubDependencies | None = None,
    config: ApiConfig | None = None,
    *,
    raise_server_exceptions: bool = False,
) -> Iterator[TestClient]:
    app = make_stub_app(stubs if stubs is not None else StubDependencies(), config)
    with TestClient(app, raise_server_exceptions=raise_server_exceptions) as client:
        yield client

"""`api` のテストの共通部品。

本物の `JobAdmission`・`JobCancellation`・`LockRelease`・`SourceStore` を、メモリ上の Repository と
固定時計で組み立て、`TestClient` で HTTP として呼ぶ。ジョブ記録・ロック・設定・メンテナンスフラグは
`JobsEnv`(`tests/jobs/support.py`)で直接置く。想定外の例外はサーバ側で 500 にする
(`raise_server_exceptions=False`。本番と同じ)。
"""

import itertools
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from loreley_crawler.api import ApiDependencies, create_app
from loreley_crawler.connectors.registry import ConnectorRegistry
from loreley_crawler.jobs import JobAdmission, JobCancellation, LockRelease
from loreley_crawler.sources import SourceStore
from tests.fakes.fake_connector import FakeConnectorType
from tests.fakes.in_memory_repository import InMemoryRepository
from tests.jobs.support import (
    NO_WAIT_RETRIER,
    TOKEN,
    JobsEnv,
    make_env,
)

SOURCE_ID = "docs"
CONNECTOR_TYPE = "file_system"
# 応答・ログに出てはならない値(センチネル)。
CONFIG_SECRET = "SENTINEL-connector-config-secret"
BODY_SENTINEL = "SENTINEL-request-body-value"


def counting_tokens() -> Callable[[], str]:
    """最初は `TOKEN`(`ADMITTED_JOB_ID` の元)、以後は 1 ずつ増える。同じ ID の再受付は、応答喪失の
    再送とみなされ成功になるので、2 回目の受付が別のジョブ ID になるようにする。"""
    numbers = itertools.count(int(TOKEN, 16))
    return lambda: f"{next(numbers):08x}"


def new_source_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "source_id": "docs-share",
        "connector_type": CONNECTOR_TYPE,
        "connector_config": {"root": "/data"},
        "ttl": 2_592_000,
        "ratio_threshold": 0.3,
        "min_delete_count": 10,
        "schedule_cron": "0 3 * * *",
    }
    body.update(overrides)
    return body


def update_body(**overrides: Any) -> dict[str, Any]:
    body = new_source_body(**overrides)
    for name in ("source_id", "connector_type"):
        if name not in overrides:
            del body[name]
    return body


@dataclass
class ApiEnv:
    jobs: JobsEnv
    connector_type: FakeConnectorType
    source_store: SourceStore
    dependencies: ApiDependencies
    app: FastAPI
    client: TestClient

    @property
    def sources_repository(self) -> InMemoryRepository:
        return self.jobs.sources_repository

    def post(self, path: str, body: Any = None, *, raw: bytes | None = None) -> Any:
        return self.client.post(path, content=_encode(body, raw))

    def put(self, path: str, body: Any = None, *, raw: bytes | None = None) -> Any:
        return self.client.put(path, content=_encode(body, raw))


def _encode(body: Any, raw: bytes | None) -> bytes:
    if raw is not None:
        return raw
    return b"" if body is None else json.dumps(body).encode("utf-8")


def make_api_env(
    jobs: JobsEnv | None = None, *, connector_type: FakeConnectorType | None = None
) -> ApiEnv:
    env = jobs or make_env()
    fake_connector_type = connector_type or FakeConnectorType()
    source_store = SourceStore(env.sources_repository, env.clock, NO_WAIT_RETRIER)
    dependencies = ApiDependencies(
        job_admission=JobAdmission(
            settings=env.settings,
            source_reader=env.source_reader,
            job_store=env.job_store,
            lock_store=env.lock_store,
            read_maintenance_flag=env.read_maintenance_flag,
            clock=env.clock,
            retrier=NO_WAIT_RETRIER,
            wakeup=env.wakeup,
            random_token=counting_tokens(),
        ),
        job_cancellation=JobCancellation(
            job_store=env.job_store,
            lock_store=env.lock_store,
            cancel_requests=env.cancel_requests,
            clock=env.clock,
            retrier=NO_WAIT_RETRIER,
        ),
        lock_release=LockRelease(
            settings=env.settings,
            job_store=env.job_store,
            lock_store=env.lock_store,
            clock=env.clock,
            retrier=NO_WAIT_RETRIER,
        ),
        source_store=source_store,
        connector_registry=ConnectorRegistry({CONNECTOR_TYPE: fake_connector_type}),
        retrier=NO_WAIT_RETRIER,
    )
    app = create_app(dependencies)
    client = TestClient(app, raise_server_exceptions=False)
    return ApiEnv(env, fake_connector_type, source_store, dependencies, app, client)

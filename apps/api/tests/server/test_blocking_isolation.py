"""Crawler の呼び出しが遅れている間も、ほかの EP と `/healthz` が応答する(C 11章 14 の server 側)。

実物の `BlockingRunner`・実際の Crawler クライアント(`HttpCrawlerClient`)・ローカル HTTP スタブで、
アプリ全体を動かす。ブロッキングの呼び出しがイベントループを塞ぐ・区分の枠を取り合う、という
退行を捕まえる。`crawler` の枠を使い切っても、`opensearch` の枠の読み取り EP は待たされない
(区分ごとの枠を小さくして、Crawler の呼び出しが別の区分で実行される退行も捕まえる)。
"""

import json
import time
from collections.abc import AsyncIterator, Iterator

import anyio
import httpx2
import pytest
from fastapi import FastAPI

from loreley_api.admin import ADMIN_API_PREFIX, create_admin_app
from loreley_api.common.concurrency import (
    CATEGORY_CRAWLER,
    CATEGORY_OPENSEARCH,
    CATEGORY_PROBE,
    BlockingRunner,
)
from loreley_api.health import create_health_router
from loreley_api.infrastructure.crawler_client import CrawlerClientConfig, HttpCrawlerClient
from loreley_api.server import SubAppMount, create_app
from tests.admin.factories import make_admin_dependencies
from tests.admin.write_requests import crawler_accepted_body
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.local_http_server import LocalHttpServer, StubReply, local_http_server

pytestmark = pytest.mark.anyio

CRAWLER_DELAY_SECONDS = 1.5
# 区分ごとの枠を同じ小さい値にする。Crawler の呼び出しが誤って別の区分(`opensearch` など)で
# 実行されると、その枠を使い切って読み取りが待たされるので、区分の取り違えが顕在化する。
CATEGORY_LIMIT = 2
CATEGORY_LIMITS = {
    CATEGORY_OPENSEARCH: CATEGORY_LIMIT,
    CATEGORY_CRAWLER: CATEGORY_LIMIT,
    CATEGORY_PROBE: CATEGORY_LIMIT,
}
# `crawler` の枠を使い切り、さらに待たせるための同時の起動数。
NUM_CONCURRENT_STARTS = CATEGORY_LIMIT + 2
WAIT_LIMIT_SECONDS = 10.0


@pytest.fixture
def slow_crawler() -> Iterator[LocalHttpServer]:
    with local_http_server() as stub:
        stub.set_default_reply(
            StubReply(
                202,
                json.dumps(crawler_accepted_body(force_delete=False)).encode(),
                {"Content-Type": "application/json"},
                delay_seconds=CRAWLER_DELAY_SECONDS,
            )
        )
        yield stub


@pytest.fixture
def app(slow_crawler: LocalHttpServer) -> Iterator[FastAPI]:
    crawler = HttpCrawlerClient(CrawlerClientConfig(slow_crawler.url, 3.0, 10.0))
    deps = make_admin_dependencies(
        InMemoryReaders(), FixedClock(), BlockingRunner(CATEGORY_LIMITS), crawler=crawler
    )
    yield create_app(
        routers=[create_health_router()],
        mounts=[SubAppMount(ADMIN_API_PREFIX, create_admin_app(deps))],
    )
    crawler.close()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx2.AsyncClient]:
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


async def wait_until_the_crawler_has_received(stub: LocalHttpServer, num_requests: int) -> None:
    with anyio.fail_after(WAIT_LIMIT_SECONDS):
        while len(stub.requests) < num_requests:
            await anyio.sleep(0.01)


async def test_reads_and_the_health_check_respond_while_every_crawler_slot_is_busy(
    client: httpx2.AsyncClient, slow_crawler: LocalHttpServer
) -> None:
    start_statuses: list[int] = []
    read_statuses: dict[str, int] = {}

    async def start_crawl(source_id: str) -> None:
        response = await client.post(f"{ADMIN_API_PREFIX}/sources/{source_id}/crawl-jobs")
        start_statuses.append(response.status_code)

    async def read(path: str) -> None:
        response = await client.get(path)
        read_statuses[path] = response.status_code

    async with anyio.create_task_group() as task_group:
        for index in range(NUM_CONCURRENT_STARTS):
            task_group.start_soon(start_crawl, f"docs-{index}")
        # 枠の分だけが Crawler に届き、残りは枠の空きを待っている。
        await wait_until_the_crawler_has_received(slow_crawler, CATEGORY_LIMIT)
        started_at = time.monotonic()

        paths = ["/healthz", f"{ADMIN_API_PREFIX}/sources", f"{ADMIN_API_PREFIX}/meta"]
        for path in paths:
            await read(path)
        reads_took_seconds = time.monotonic() - started_at
        num_starts_finished_at_the_reads = len(start_statuses)

    assert read_statuses == dict.fromkeys(paths, 200)
    # 読み取りが終わった時点で、遅い Crawler の呼び出しは 1 つも終わっていない(待たされていない)。
    assert num_starts_finished_at_the_reads == 0
    assert reads_took_seconds < CRAWLER_DELAY_SECONDS
    # 遅い呼び出しは、枠の順番が来て、すべて受け付けられる。
    assert start_statuses == [202] * NUM_CONCURRENT_STARTS
    assert len(slow_crawler.requests) == NUM_CONCURRENT_STARTS


async def test_a_crawler_call_in_flight_does_not_block_the_event_loop(
    client: httpx2.AsyncClient, slow_crawler: LocalHttpServer
) -> None:
    """イベントループが塞がれていれば、遅延の間はタイマーも進まない。"""
    num_ticks = 0
    is_crawl_finished = False

    async def count_ticks() -> None:
        nonlocal num_ticks
        while not is_crawl_finished:
            await anyio.sleep(0.05)
            num_ticks += 1

    async def start_crawl() -> None:
        nonlocal is_crawl_finished
        response = await client.post(f"{ADMIN_API_PREFIX}/sources/docs/crawl-jobs")
        assert response.status_code == 202
        is_crawl_finished = True

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(count_ticks)
        task_group.start_soon(start_crawl)

    # 遅延の間(1.5 秒)、50 ミリ秒ごとのタイマーが進む(塞がれていれば 0〜数回)。
    assert num_ticks >= 10
    assert len(slow_crawler.requests) == 1

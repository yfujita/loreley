"""admin のテストの共有フィクスチャ(偽の Reader・固定時計・`InlineRunner` で組み立てる)。"""

import pytest
from fastapi.testclient import TestClient

from loreley_api.admin import create_admin_app
from loreley_api.server import SubAppMount, create_app
from tests.admin.factories import ADMIN_PREFIX, make_admin_dependencies
from tests.fakes.clock import FixedClock
from tests.fakes.in_memory_readers import InMemoryReaders
from tests.fakes.inline_runner import InlineRunner


@pytest.fixture
def anyio_backend() -> str:
    """`@pytest.mark.anyio` のテストは asyncio で動かす(trio は使わない)。"""
    return "asyncio"


@pytest.fixture
def readers() -> InMemoryReaders:
    return InMemoryReaders()


@pytest.fixture
def client(
    readers: InMemoryReaders, fixed_clock: FixedClock, inline_runner: InlineRunner
) -> TestClient:
    """外側のアプリにマウントした Admin API(本番と同じ共通ハンドラ・`no-store`)。"""
    deps = make_admin_dependencies(readers, fixed_clock, inline_runner)
    return TestClient(create_app(mounts=[SubAppMount(ADMIN_PREFIX, create_admin_app(deps))]))

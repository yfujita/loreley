from collections.abc import Iterator

import pytest

from tests.crawl.support import CrawlEnv, crawl_env


@pytest.fixture
def env() -> Iterator[CrawlEnv]:
    """ファイルのない既定の環境(個別の列挙・設定が要るテストは `crawl_env(...)` を直接使う)。"""
    with crawl_env() as environment:
        yield environment

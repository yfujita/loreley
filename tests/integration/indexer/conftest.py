"""結合テストの共通フィクスチャ。

前提: compose で `opensearch`・`opensearch-init`・`indexer` が起動済みであること。
テストは、起動済みのスタックに 127.0.0.1 経由でつなぐ(スタックの起動・停止は、このディレクトリの
README と `scripts/run-indexer-integration-test.sh` が担当する。ここでは起動しない)。

共通部品(Crawler 役のクライアント、OpenSearch の検証ヘルパ、`document_id` の独立実装)は
`support.py` にある。
"""

from collections.abc import Iterator

import httpx
import pytest

from support import (
    INDEXER_URL,
    OPENSEARCH_URL,
    CrawlerClient,
    OpenSearchProbe,
    unique_id,
)

STACK_HINT = (
    "compose のスタックが起動していません。先に次のどちらかで起動してください。\n"
    "  - scripts/run-indexer-integration-test.sh(起動 → テスト → 後片付けを一括で行う)\n"
    "  - docker compose -p loreley-it -f deploy/compose/compose.yaml "
    "-f tests/integration/indexer/compose.test.yaml up -d --build"
)


@pytest.fixture(scope="session", autouse=True)
def stack_is_up() -> None:
    """OpenSearch と Indexer に疎通できなければ、原因の分かるメッセージで全体を中止する。

    個々のテストが接続エラーで大量に失敗すると原因が埋もれるため、最初に 1 回だけ確認する。
    """
    checks = {
        "OpenSearch": f"{OPENSEARCH_URL}/_cluster/health",
        "Indexer": f"{INDEXER_URL}/healthz",
    }
    for name, url in checks.items():
        try:
            response = httpx.get(url, timeout=5.0)
        except httpx.HTTPError as error:
            pytest.exit(f"{name} に接続できません ({url}): {error!r}\n{STACK_HINT}", returncode=2)
        if response.status_code != 200:
            detail = f"{response.status_code} {response.text[:200]}"
            pytest.exit(f"{name} が 200 を返しません ({url}): {detail}\n{STACK_HINT}", returncode=2)


@pytest.fixture(scope="session")
def indexer() -> Iterator[httpx.Client]:
    """Indexer の HTTP クライアント。タイムアウトは、抽出や削除の待ちに十分な 30 秒。"""
    with httpx.Client(base_url=INDEXER_URL, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="session")
def opensearch() -> Iterator[OpenSearchProbe]:
    probe = OpenSearchProbe(OPENSEARCH_URL)
    yield probe
    probe.close()


@pytest.fixture
def crawler(indexer: httpx.Client, opensearch: OpenSearchProbe) -> CrawlerClient:
    return CrawlerClient(indexer, opensearch)


@pytest.fixture
def source_id(request: pytest.FixtureRequest) -> str:
    """このテスト専用の `source_id`。他のテストのデータ(件数・削除対象)と干渉しない。"""
    return unique_id(f"src-{request.node.name}")


@pytest.fixture
def other_source_id(request: pytest.FixtureRequest) -> str:
    """「他のソースは影響を受けない」ことの確認に使う、もう 1 つの専用 `source_id`。"""
    return unique_id(f"other-{request.node.name}")

"""結合テストの共通フィクスチャ。

前提: compose で `opensearch`・`opensearch-init`・`indexer`・`crawler` が起動済みで、`crawler` が
healthy であること。テストは、起動済みのスタックに 127.0.0.1 経由でつなぐ(スタックの起動・停止は、
このディレクトリの README と `scripts/run-crawler-integration-test.sh` が担当する。
ここでは起動しない)。

共通部品(OpenSearch の検証ヘルパ、Crawler の API クライアント、`document_id` の独立実装、検索対象の
ディレクトリ)は `support.py` にある。
"""

from collections.abc import Iterator

import httpx
import pytest

from support import (
    CRAWLER_URL,
    DOCUMENTS_DIR,
    INDEXER_URL,
    JOBS_INDEX,
    MAINTENANCE_RECORD_ID,
    OPENSEARCH_URL,
    CrawlerApi,
    OpenSearchProbe,
    SourceDirectory,
    register_source,
    unique_id,
)

STACK_HINT = (
    "compose のスタックが起動していません。先に次のどちらかで起動してください。\n"
    "  - scripts/run-crawler-integration-test.sh(起動 → テスト → 後片付けを一括で行う)\n"
    "  - mkdir -p tests/integration/crawler/data && \\\n"
    "    CRAWLER_DOCUMENTS_DIR=$PWD/tests/integration/crawler/data \\\n"
    "    docker compose -p loreley-it -f deploy/compose/compose.yaml "
    "-f tests/integration/crawler/compose.test.yaml up -d --build"
)


@pytest.fixture(scope="session", autouse=True)
def stack_is_up() -> None:
    """スタックに疎通でき、テストを始められる状態かを、最初に 1 回だけ確認する。

    個々のテストが接続エラーで大量に失敗すると原因が埋もれるため、原因の分かるメッセージで全体を中止する。
    """
    checks = {
        "OpenSearch": f"{OPENSEARCH_URL}/_cluster/health",
        "Indexer": f"{INDEXER_URL}/healthz",
        "Crawler": f"{CRAWLER_URL}/healthz",
    }
    for name, url in checks.items():
        try:
            response = httpx.get(url, timeout=5.0)
        except httpx.HTTPError as error:
            pytest.exit(f"{name} に接続できません ({url}): {error!r}\n{STACK_HINT}", returncode=2)
        if response.status_code != 200:
            detail = f"{response.status_code} {response.text[:200]}"
            pytest.exit(f"{name} が 200 を返しません ({url}): {detail}\n{STACK_HINT}", returncode=2)

    if not DOCUMENTS_DIR.is_dir():
        pytest.exit(
            f"検索対象のディレクトリがありません ({DOCUMENTS_DIR})。Crawler に mount するため、"
            "先に作成し、compose の CRAWLER_DOCUMENTS_DIR に同じパスを渡してください。\n"
            f"{STACK_HINT}",
            returncode=2,
        )

    # 前回の実行が中断してメンテナンスフラグが残っていると、すべてのクロール起動が 409 になる。
    flag = httpx.get(f"{OPENSEARCH_URL}/{JOBS_INDEX}/_doc/{MAINTENANCE_RECORD_ID}", timeout=5.0)
    if flag.status_code == 200:
        pytest.exit(
            "メンテナンスフラグが残っています(前回の実行が中断した可能性)。残ったままだと、すべての"
            f"クロール起動が 409 になります。\n  DELETE {OPENSEARCH_URL}/{JOBS_INDEX}/_doc/"
            f"{MAINTENANCE_RECORD_ID} で消すか、スタックを down -v して作り直してください。",
            returncode=2,
        )


@pytest.fixture(scope="session")
def crawler_api() -> Iterator[CrawlerApi]:
    """Crawler の HTTP クライアント。クロールの起動は 202 で即座に返る(完了は待たない)。"""
    with httpx.Client(base_url=CRAWLER_URL, timeout=30.0) as client:
        yield CrawlerApi(client)


@pytest.fixture(scope="session")
def opensearch() -> Iterator[OpenSearchProbe]:
    probe = OpenSearchProbe(OPENSEARCH_URL)
    yield probe
    probe.close()


@pytest.fixture
def source_id(request: pytest.FixtureRequest) -> str:
    """このテスト専用の `source_id`。他のテスト・前の実行のデータ(件数・削除対象)と干渉しない。"""
    return unique_id(f"src-{request.node.name}")


@pytest.fixture
def other_source_id(request: pytest.FixtureRequest) -> str:
    """「他のソースは影響を受けない」ことの確認に使う、もう 1 つの専用 `source_id`。"""
    return unique_id(f"other-{request.node.name}")


@pytest.fixture
def source_directory(source_id: str) -> Iterator[SourceDirectory]:
    """`source_id` の検索対象ディレクトリ(空で作成し、テストの後に削除する)。"""
    directory = SourceDirectory(source_id)
    directory.create()
    yield directory
    directory.cleanup()


@pytest.fixture
def other_source_directory(other_source_id: str) -> Iterator[SourceDirectory]:
    directory = SourceDirectory(other_source_id)
    directory.create()
    yield directory
    directory.cleanup()


@pytest.fixture
def registered_source(
    crawler_api: CrawlerApi, source_directory: SourceDirectory
) -> SourceDirectory:
    """既定の設定(`file_system`、ttl=600)で登録済みの `source_id` の検索対象ディレクトリ。

    ディレクトリは空で、テストがファイルを置いてからクロールを起動する。登録の確認(201 と保存内容)は
    CIT-10 が行うので、ここでは 201 だけを確認する。
    """
    register_source(crawler_api, source_directory)
    return source_directory

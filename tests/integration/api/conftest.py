"""結合テストの共通フィクスチャ。

前提: compose で `opensearch`・`opensearch-init`・`indexer`・`crawler`・`api`・`web` が起動済みで、
`crawler`・`api`・`web` が healthy であること。テストは、起動済みのスタックに 127.0.0.1 経由でつなぐ
(スタックの起動・停止は、`scripts/run-api-integration-test.sh` が担当する。ここでは起動しない)。

共通部品(Admin API のクライアント、OpenSearch の検証ヘルパ、`document_id` の独立実装、検索対象の
ディレクトリ、待ち、障害系の `ComposeControl`)は `support.py` にある。
"""

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from support import (
    ADMIN_API_URL,
    CRAWLER_URL,
    DOCUMENTS_DIR,
    INDEXER_URL,
    OPENSEARCH_URL,
    AdminApi,
    ComposeControl,
    OpenSearchProbe,
    SourceDirectory,
    is_compose_control_allowed,
    register_source,
    unique_id,
    wait_for_idle,
)

STACK_HINT = (
    "compose のスタックが起動していません。先に scripts/run-api-integration-test.sh"
    "(起動 → テスト → 後片付けを一括で行う)で実行するか、--keep で起動したスタックに対して"
    "実行してください。"
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
        "api": f"{ADMIN_API_URL}/healthz",
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
    with OpenSearchProbe(OPENSEARCH_URL) as probe:
        if probe.maintenance_flag_exists():
            pytest.exit(
                "メンテナンスフラグが残っています(前回の実行が中断した可能性)。残ったままだと、すべての"
                "クロール起動が 409 になります。スタックを down -v して作り直してください。",
                returncode=2,
            )


@pytest.fixture(scope="session")
def api() -> Iterator[AdminApi]:
    """Admin API の HTTP クライアント。"""
    with httpx.Client(base_url=ADMIN_API_URL, timeout=30.0) as client:
        yield AdminApi(client)


@pytest.fixture(scope="session")
def opensearch() -> Iterator[OpenSearchProbe]:
    with OpenSearchProbe(OPENSEARCH_URL) as probe:
        yield probe


@pytest.fixture(autouse=True)
def idle_before_and_after_each_test(api: AdminApi) -> Iterator[None]:
    """各テストの前後で、実行中・実行待ちのジョブが 0 になるのを待つ。

    Job Runner は直列なので、前のテストのジョブが残っていると、次のテストの実行の窓を乱す。
    後も待つのは、テストの失敗で止めたジョブを次のテストへ持ち越さないため。
    """
    wait_for_idle(api)
    yield
    wait_for_idle(api)


@pytest.fixture(scope="session")
def compose_control() -> ComposeControl:
    """障害系(`test_90_*`)だけが使う。スクリプトが許可していない実行では skip する。"""
    if not is_compose_control_allowed():
        pytest.skip("LORELEY_IT_ALLOW_COMPOSE_CONTROL=1 でないため、コンテナの停止・起動は行わない")
    return ComposeControl()


@pytest.fixture
def source_id(request: pytest.FixtureRequest) -> str:
    """このテスト専用の `source_id`。他のテスト・前の実行のデータ(件数・削除対象)と干渉しない。"""
    return unique_id(f"src-{request.node.name}")


@pytest.fixture
def source_directory(source_id: str) -> Iterator[SourceDirectory]:
    """`source_id` の検索対象ディレクトリ(空で作成し、テストの後に削除する)。"""
    directory = SourceDirectory(source_id)
    directory.create()
    yield directory
    directory.cleanup()


@pytest.fixture
def registered_source(api: AdminApi, source_directory: SourceDirectory) -> SourceDirectory:
    """既定の設定(`file_system`、ttl=600 秒)で、EP-03 により登録済みの検索対象ディレクトリ。

    ディレクトリは空で、テストがファイルを置いてからクロールを起動する。登録の確認(保存内容など)は
    AIT-10 が行うので、ここでは 201 だけを確認する。
    """
    register_source(api, source_directory)
    return source_directory


@pytest.fixture
def make_registered_source(
    api: AdminApi, request: pytest.FixtureRequest
) -> Iterator[Callable[..., SourceDirectory]]:
    """同じテストで、登録済みのソースを追加で作る関数(実行待ち・別ソースの状態を作るテスト用)。

    `make(label, **overrides)` は、`label` を含む一意の `source_id` で空のディレクトリを作り、
    EP-03 で登録して返す(`overrides` は `source_settings` の上書き)。ディレクトリは、テストの後に
    削除する。
    """
    created: list[SourceDirectory] = []

    def make(label: str, **overrides: Any) -> SourceDirectory:
        directory = SourceDirectory(unique_id(f"{label}-{request.node.name}"))
        directory.create()
        created.append(directory)
        register_source(api, directory, **overrides)
        return directory

    yield make
    for directory in created:
        directory.cleanup()

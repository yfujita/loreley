"""`python -m loreley_crawler.main` を、実際のプロセスとして起動する(異常終了の確認)。

どれも HTTP を開く前に非 0 で終わる。外のシステムは使わない(接続先は、閉じたローカルのポート)。
"""

import os
import socket
import subprocess
import sys
from pathlib import Path

from tests.main.conftest import PREFIX
from tests.main.support import OPENSEARCH_PASSWORD

PROCESS_TIMEOUT_SECONDS = 60
CRAWLER_SRC = Path(__file__).resolve().parents[2] / "src"


def closed_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def run_main(**env: str) -> subprocess.CompletedProcess[str]:
    environment = {name: value for name, value in os.environ.items() if not name.startswith(PREFIX)}
    # インストール済みでなくても動くよう、`src` を `PYTHONPATH` に入れる(`--no-install-project`)。
    environment["PYTHONPATH"] = str(CRAWLER_SRC)
    environment.update({PREFIX + name.upper(): value for name, value in env.items()})
    return subprocess.run(
        [sys.executable, "-m", "loreley_crawler.main"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=PROCESS_TIMEOUT_SECONDS,
        check=False,
    )


def test_a_missing_required_setting_exits_non_zero_with_a_fixed_message() -> None:
    result = run_main(opensearch_url="http://127.0.0.1:1", indexer_url="http://127.0.0.1:2")

    assert result.returncode != 0
    assert "ConfigError: invalid settings: LORELEY_CRAWLER_OWNER: missing" in result.stderr


def test_an_unset_owner_with_a_password_never_prints_the_password() -> None:
    result = run_main(
        opensearch_url="http://127.0.0.1:1",
        indexer_url="http://127.0.0.1:2",
        opensearch_username="crawler",
        opensearch_password=OPENSEARCH_PASSWORD,
    )

    assert result.returncode != 0
    assert OPENSEARCH_PASSWORD not in result.stderr + result.stdout


def test_a_consistency_violation_exits_non_zero_naming_the_item_and_the_numbers() -> None:
    result = run_main(
        owner="crawler-1",
        opensearch_url="http://127.0.0.1:1",
        indexer_url="http://127.0.0.1:2",
        batch_max_documents="51",
        indexer_max_batch_documents="50",
    )

    assert result.returncode != 0
    assert "batch_max_documents=51 exceeds MAX_BATCH_DOCUMENTS=50" in result.stderr


def test_an_unreachable_opensearch_exits_non_zero_before_http_opens() -> None:
    """起動時の回復が Store 層につながらず、HTTP を開く前に異常終了する。"""
    result = run_main(
        owner="crawler-1",
        opensearch_url=f"http://127.0.0.1:{closed_port()}",
        indexer_url="http://127.0.0.1:2",
        http_port=str(closed_port()),
        retry_initial_backoff_seconds="0",
        retry_max_backoff_seconds="0",
        opensearch_username="crawler",
        opensearch_password=OPENSEARCH_PASSWORD,
    )

    assert result.returncode != 0
    assert "StoreUnavailableError" in result.stderr
    assert "starting the HTTP server" not in result.stderr
    assert OPENSEARCH_PASSWORD not in result.stderr + result.stdout

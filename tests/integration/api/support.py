"""結合テストの共通部品(テストから import して使う。pytest のフィクスチャは conftest.py)。

含むもの:
  - 接続先・索引名・待ちの上限などの定数
  - `document_id` の**独立実装**(api・Crawler・Indexer のコードは import しない。実装の誤りを
    テストが同じ誤りで見逃さないため)
  - Admin API の HTTP クライアント(`AdminApi`。14 エンドポイントと `/healthz`)
  - OpenSearch を直接読む検証ヘルパ(`OpenSearchProbe`。書き込みは前提作りの 2 つだけ)
  - 検索対象のディレクトリを `source_id` ごとに作る `SourceDirectory`
  - 応答の検査(`expect_json`・`expect_error`)と、待ち(`poll_until` と各待ちヘルパ)
  - 障害系だけが使う `ComposeControl`(`docker compose stop/start`。許可リストとプロジェクトを固定)

設計上の位置づけ:
  Admin API は書き込みをすべて Crawler の HTTP 経由で行い、読み取りは OpenSearch を直接読む
  (admin-api 1.1)。そのため、判定は Admin API の応答を主とし、必要なものは OpenSearch の実データを
  テストが直接読んで独立に計算した期待値と照合する。Crawler の API は、テストから直接呼ばない。
"""

import hashlib
import os
import re
import shutil
import subprocess
import time
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

# --- 接続先(compose が 127.0.0.1 だけに publish したポート。環境変数で上書きできる) ---
ADMIN_API_URL = os.environ.get("LORELEY_IT_API_URL", "http://127.0.0.1:8080")
CRAWLER_URL = os.environ.get("LORELEY_IT_CRAWLER_URL", "http://127.0.0.1:8001")
INDEXER_URL = os.environ.get("LORELEY_IT_INDEXER_URL", "http://127.0.0.1:8000")
OPENSEARCH_URL = os.environ.get("LORELEY_IT_OPENSEARCH_URL", "http://127.0.0.1:9200")

# Admin API のパスは、このプレフィックス配下(`/healthz` だけがルート直下)。
ADMIN_API_PREFIX = "/api/admin/v1"

# --- 索引名(検索インデックスはエイリアス。infra/opensearch の init が作る) ---
# compose で変えられるが、一括スクリプトは既定値に固定する。手動で変えたときは、compose と同じ
# 環境変数を pytest にも渡す(未指定は compose の既定)。
SEARCH_INDEX = os.environ.get("LORELEY_SEARCH_INDEX_ALIAS", "loreley-documents")
DELETIONS_INDEX = os.environ.get("LORELEY_DELETIONS_INDEX_NAME", "loreley-deletions")
JOBS_INDEX = os.environ.get("LORELEY_JOBS_INDEX_NAME", "loreley-jobs")
SOURCES_INDEX = os.environ.get("LORELEY_SOURCES_INDEX_NAME", "loreley-sources")
MAINTENANCE_RECORD_ID = "maintenance"

# --- 検索対象のディレクトリ ---
# ホスト側は compose の `CRAWLER_DOCUMENTS_DIR`(スクリプトが export する)と同じ場所。
# Crawler はこれを `:ro` で `/data/documents` に mount している(api は mount しない)。
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS_DIR = Path(os.environ.get("CRAWLER_DOCUMENTS_DIR") or Path(__file__).parent / "data")
CONTAINER_DOCUMENTS_ROOT = "/data/documents"

# --- 待ち(間隔と上限を明示する。上限を超えたら、最後の状態つきで失敗させる) ---
# ジョブの完了。compose.test.yaml のポーリング上限(120 秒)より短くし、Crawler の失敗でジョブが
# 居座ったときは、Crawler 側の打ち切りより先にテストが原因つきで失敗する。
# クロール 1 回は約 10〜12 秒。
JOB_WAIT_TIMEOUT_SECONDS = 90.0
JOB_POLL_INTERVAL_SECONDS = 0.5
# `running` の観測(起動 202 から Job Runner が実行を始めるまで)。
RUNNING_WAIT_TIMEOUT_SECONDS = 30.0
RUNNING_POLL_INTERVAL_SECONDS = 0.2
# ロックの解放。ジョブ記録が終端になった後に Job Runner が解放する。
LOCK_WAIT_TIMEOUT_SECONDS = 30.0
LOCK_POLL_INTERVAL_SECONDS = 0.2
# アイドル(実行中・実行待ちのジョブが 0)。前のテストのジョブが残っていても、1 回分のクロールは
# 終わる長さにする(ポーリング上限 120 秒より短く、ジョブ待ちより長い)。
IDLE_WAIT_TIMEOUT_SECONDS = 120.0
IDLE_POLL_INTERVAL_SECONDS = 0.5
# 検索(`search`・`msearch`)で読む EP(EP-01・09・11 と、EP-02 の最終クロール・文書数)は、書き込みの
# 反映が最大約 1 秒遅れる(OpenSearch の refresh。admin-api-architecture AAA-P-6。Admin API は
# refresh を呼ばない)。反映を待つ上限と間隔。
READ_LAG_TIMEOUT_SECONDS = 10.0
READ_LAG_POLL_INTERVAL_SECONDS = 0.3
# TTL の経過を待つ。経過の判定は秒単位(HTTP の `Date`)なので、余裕を足して、判定の直後の削除で
# 確実に期限切れになるようにする。上限は、TTL に足す分(最初の確認までの遅れ)。
EXPIRY_MARGIN_SECONDS = 2.0
EXPIRY_WAIT_EXTRA_SECONDS = 30.0
EXPIRY_POLL_INTERVAL_SECONDS = 1.0
# 停止したサービスが再び healthy になるまで。OpenSearch の停止後は、Crawler・Indexer が
# 接続できるようになるまで最大約 3 分かかる(起動時の回復)。
SERVICE_RECOVERY_TIMEOUT_SECONDS = 300.0
SERVICE_RECOVERY_POLL_INTERVAL_SECONDS = 2.0

TERMINAL_JOB_STATUSES = frozenset({"succeeded", "partially_succeeded", "failed", "cancelled"})


# --- ID ---


def unique_id(prefix: str) -> str:
    """テストごとに一意な ID。前のテスト・前の実行のデータと干渉しない。

    `source_id` の文字種(半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ。crawler-api 3.2)を
    満たす。
    """
    safe_prefix = re.sub(r"[^A-Za-z0-9]+", "-", prefix).strip("-").lower()[:40]
    return f"it-{safe_prefix}-{uuid.uuid4().hex[:10]}"


def compute_document_id(source_id: str, external_id: str) -> str:
    """`document_id` の独立実装(interface 5.2)。

    SHA-256(`source_id` + NUL + `external_id`) の小文字 16 進。`external_id` はハッシュの前に
    NFC へ正規化し、`\\` を `/` に統一する。FileSystem Connector の `external_id` は、`root` からの
    相対パス(例 `nested/sample-nested.txt`)。
    """
    normalized = unicodedata.normalize("NFC", external_id).replace("\\", "/")
    return hashlib.sha256(f"{source_id}\0{normalized}".encode()).hexdigest()


def parse_instant(value: str) -> datetime:
    """Admin API・OpenSearch の ISO 8601(`Z` 終わり)を、タイムゾーンつきの日時にする。"""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def format_instant(value: datetime) -> str:
    """直接書き込む記録の日時。Crawler が書く形(UTC・ミリ秒・`Z` 終わり)に合わせる。"""
    utc_value = value.astimezone(UTC)
    return utc_value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_value.microsecond // 1000:03d}Z"


# --- 応答の検査 ---


def expect_json(response: httpx.Response, expected_status: int) -> Any:
    """ステータスコードを検査して、JSON を返す。違えば、応答本文つきで失敗させる。"""
    assert response.status_code == expected_status, (
        f"{response.request.method} {response.request.url.path} returned "
        f"{response.status_code} (expected {expected_status}): {response.text[:500]}"
    )
    return response.json()


def expect_error(
    response: httpx.Response,
    expected_status: int,
    expected_code: str,
    *,
    expected_retryable: bool | None = None,
) -> dict[str, Any]:
    """共通のエラー形式(admin-api 2.3・A 5.2。`error` に `code`・`message`・`retryable`)を検査する。

    `error` オブジェクトを返す(`details` の検査は、呼び出し側が行う)。
    """
    body = expect_json(response, expected_status)
    error = body.get("error")
    assert isinstance(error, dict), f"the error body must have an 'error' object: {body}"
    assert error.get("code") == expected_code, f"error code must be {expected_code}: {body}"
    assert set(error) >= {"code", "message", "retryable"}, f"error must have the 3 keys: {body}"
    if expected_retryable is not None:
        assert error["retryable"] is expected_retryable, (
            f"retryable must be {expected_retryable}: {body}"
        )
    return dict(error)


# --- 待ち ---


def poll_until[T](
    fetch: Callable[[], T],
    is_done: Callable[[T], bool],
    *,
    timeout_secs: float,
    poll_interval_secs: float,
    what: str,
) -> T:
    """`fetch` の結果が `is_done` を満たすまで、一定の間隔で繰り返す。上限を超えたら失敗させる。

    sleep だけで待たない(固定の待ちは、遅い環境で落ち、速い環境で時間を浪費するため)。
    最初に 1 回確認してから待つので、すでに条件を満たしていれば待たない。
    """
    deadline = time.monotonic() + timeout_secs
    while True:
        value = fetch()
        if is_done(value):
            return value
        if time.monotonic() >= deadline:
            raise AssertionError(
                f"{what} did not happen within {timeout_secs}s "
                f"(polling every {poll_interval_secs}s). last state: {value}"
            )
        time.sleep(poll_interval_secs)


def wait_for_job_terminal(api: "AdminApi", job_id: str) -> dict[str, Any]:
    """EP-10 のジョブが終端状態になるのを待つ。応答本文(ジョブ詳細)を返す。"""
    return poll_until(
        lambda: expect_json(api.get_job(job_id), 200),
        lambda job: job["status"] in TERMINAL_JOB_STATUSES,
        timeout_secs=JOB_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs=JOB_POLL_INTERVAL_SECONDS,
        what=f"job {job_id} reaching a terminal state",
    )


def wait_for_job_running(api: "AdminApi", job_id: str) -> dict[str, Any]:
    """EP-10 のジョブが `running` になるのを待つ(取消・競合の操作の前に、窓が開いたことを観測する)。

    すでに終端になっていたら、窓が閉じたことが分かるメッセージで失敗させる(待ち続けない)。
    """
    job = poll_until(
        lambda: expect_json(api.get_job(job_id), 200),
        lambda job: job["status"] == "running" or job["status"] in TERMINAL_JOB_STATUSES,
        timeout_secs=RUNNING_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs=RUNNING_POLL_INTERVAL_SECONDS,
        what=f"job {job_id} becoming running",
    )
    assert job["status"] == "running", (
        f"job {job_id} was already {job['status']} when first observed; the running window "
        f"(the Crawler polling interval) was missed: failure_reason={job.get('failure_reason')}"
    )
    return job


def wait_for_lock_released(opensearch: "OpenSearchProbe", source_id: str) -> None:
    """ロック文書 `lock-{source_id}` が消えるのを待つ。

    ロックの解放は、ジョブ記録が終端になった**後**に Job Runner が行う(最終状態の記録の後。
    crawler-architecture 4.5)。ジョブの完了を確認した直後は、まだ残っていることがあるため、待つ。
    """
    poll_until(
        lambda: opensearch.fetch_lock(source_id),
        lambda lock: lock is None,
        timeout_secs=LOCK_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs=LOCK_POLL_INTERVAL_SECONDS,
        what=f"the lock of {source_id} being released",
    )


def wait_for_source_listing(
    api: "AdminApi", is_ready: Callable[[dict[str, Any]], bool], *, what: str
) -> dict[str, Any]:
    """EP-01 の応答が `is_ready` を満たすまで待つ(検索で読むため、書き込みの反映が遅れる)。"""
    return poll_until(
        lambda: expect_json(api.list_sources(), 200),
        is_ready,
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what=what,
    )


def wait_for_source_detail(
    api: "AdminApi", source_id: str, is_ready: Callable[[dict[str, Any]], bool], *, what: str
) -> dict[str, Any]:
    """EP-02 の応答が `is_ready` を満たすまで待つ(最終クロール・文書数は検索で読むため遅れる)。"""
    return poll_until(
        lambda: expect_json(api.get_source(source_id), 200),
        is_ready,
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what=what,
    )


def wait_for_source_row(
    api: "AdminApi", source_id: str, is_ready: Callable[[dict[str, Any]], bool], *, what: str
) -> dict[str, Any]:
    """EP-01 の `source_id` の行が `is_ready` を満たすまで待って返す(検索で読むので遅れる)。"""

    def row_of(listing: dict[str, Any]) -> dict[str, Any] | None:
        return next((item for item in listing["items"] if item["source_id"] == source_id), None)

    listing = wait_for_source_listing(
        api, lambda body: (row := row_of(body)) is not None and is_ready(row), what=what
    )
    row = row_of(listing)
    assert row is not None
    return row


def wait_for_job_list(
    api: "AdminApi", is_ready: Callable[[dict[str, Any]], bool], *, what: str, **query: str | int
) -> dict[str, Any]:
    """EP-09 の応答が `is_ready` を満たすまで待つ(検索で読むため、書き込みの反映が遅れる)。"""
    return poll_until(
        lambda: expect_json(api.list_jobs(**query), 200),
        is_ready,
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what=what,
    )


def wait_for_document_list(
    api: "AdminApi",
    source_id: str,
    is_ready: Callable[[dict[str, Any]], bool],
    *,
    what: str,
    **query: str | int,
) -> dict[str, Any]:
    """EP-11 の応答が `is_ready` を満たすまで待つ(検索で読むため、書き込みの反映が遅れる)。"""
    return poll_until(
        lambda: expect_json(api.list_documents(source_id, **query), 200),
        is_ready,
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what=what,
    )


def wait_for_finish_notice_started(opensearch: "OpenSearchProbe", job_id: str) -> dict[str, Any]:
    """ジョブ記録に `finish_notice.send_started_at` が記録されるのを待つ(終了通知の送信の開始)。

    これ以降の取消は、Indexer の削除を止めない(crawler-architecture 4.7)。その後 Crawler は、
    削除結果をポーリングする間(間隔 10 秒)ロックを持つので、取消・競合の操作はその窓で行う。
    ジョブ記録は ID 指定で直接読む(検索ではないので反映の遅れがない)。すでに終端なら、窓を
    見逃したことが分かるメッセージで失敗させる(待ち続けない)。
    """

    def has_started_sending(record: dict[str, Any] | None) -> bool:
        if record is None:
            return False
        notice = record.get("finish_notice") or {}
        return notice.get("send_started_at") is not None or record["status"] in (
            TERMINAL_JOB_STATUSES
        )

    record = poll_until(
        lambda: opensearch.fetch_job(job_id),
        has_started_sending,
        timeout_secs=RUNNING_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs=RUNNING_POLL_INTERVAL_SECONDS,
        what=f"job {job_id} starting to send the finish notice",
    )
    assert record["status"] not in TERMINAL_JOB_STATUSES, (
        f"job {job_id} was already {record['status']} when first observed; the window after the "
        f"finish notice (the Crawler polling interval) was missed: "
        f"failure_reason={record.get('failure_reason')}"
    )
    return record


def wait_until_expired(api: "AdminApi", last_seen_at: datetime, ttl_seconds: int) -> None:
    """`last_seen_at + TTL` が過ぎるまで待つ(実時間が過ぎるのを待つ。上限つきのポーリング)。

    現在時刻は api の応答の `Date` から読む。`last_seen_at` を決めた Crawler・判定する Indexer と
    同じ Docker の時計なので、ホストの時計がずれていても結果が変わらない。
    """
    expiry_at = last_seen_at + timedelta(seconds=ttl_seconds + EXPIRY_MARGIN_SECONDS)
    poll_until(
        api.server_now,
        lambda now: now > expiry_at,
        timeout_secs=ttl_seconds + EXPIRY_WAIT_EXTRA_SECONDS,
        poll_interval_secs=EXPIRY_POLL_INTERVAL_SECONDS,
        what=f"the TTL ({ttl_seconds}s) of last_seen_at={last_seen_at.isoformat()} passing",
    )


def wait_for_idle(api: "AdminApi") -> dict[str, Any]:
    """実行中・実行待ちのジョブが 0 になるのを待つ(EP-09 `status=active` の `total`)。

    Job Runner は直列なので、前のテストのジョブが残っていると、次のテストの実行の窓を乱す。
    """
    return poll_until(
        lambda: expect_json(api.list_jobs(status="active"), 200),
        lambda jobs: jobs["total"] == 0,
        timeout_secs=IDLE_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs=IDLE_POLL_INTERVAL_SECONDS,
        what="no running or queued jobs",
    )


# --- Admin API の HTTP クライアント ---


class AdminApi:
    """Admin API(admin-api 1.1 の EP-01〜14)と `/healthz` のクライアント。応答は検査せずに返す。

    クエリは、渡した名前をそのまま送る(未知のクエリの 400 を確認できるよう、ここでは検証しない)。
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def healthz(self) -> httpx.Response:
        return self._client.get("/healthz")

    def server_now(self) -> datetime:
        """api の時計での現在時刻(`/healthz` の応答の `Date`。秒単位)。"""
        response = self._client.get("/healthz")
        return parsedate_to_datetime(response.headers["date"])

    def openapi_json(self) -> httpx.Response:
        """`OPENAPI_ENABLED` が既定(無効)のとき 404 になる。"""
        return self._client.get(f"{ADMIN_API_PREFIX}/openapi.json")

    # --- sources(EP-01〜05) ---

    def list_sources(self) -> httpx.Response:
        return self._client.get(f"{ADMIN_API_PREFIX}/sources")

    def get_source(self, source_id: str) -> httpx.Response:
        return self._client.get(f"{ADMIN_API_PREFIX}/sources/{source_id}")

    def register_source(self, body: dict[str, Any]) -> httpx.Response:
        return self._client.post(f"{ADMIN_API_PREFIX}/sources", json=body)

    def update_source(self, source_id: str, body: dict[str, Any]) -> httpx.Response:
        return self._client.put(f"{ADMIN_API_PREFIX}/sources/{source_id}", json=body)

    def start_source_delete(self, source_id: str) -> httpx.Response:
        return self._client.post(f"{ADMIN_API_PREFIX}/sources/{source_id}/delete-jobs")

    # --- クロール操作(EP-06〜08) ---

    def start_crawl(self, source_id: str, body: dict[str, Any] | None = None) -> httpx.Response:
        """`body` が None なら本文なし(`{}` と同じ。`force_delete`・`rewrite_mode` は false)。"""
        return self._client.post(f"{ADMIN_API_PREFIX}/sources/{source_id}/crawl-jobs", json=body)

    def cancel_job(self, job_id: str) -> httpx.Response:
        return self._client.post(f"{ADMIN_API_PREFIX}/jobs/{job_id}/cancel")

    def release_lock(self, source_id: str) -> httpx.Response:
        return self._client.delete(f"{ADMIN_API_PREFIX}/sources/{source_id}/lock")

    # --- jobs(EP-09・10) ---

    def list_jobs(self, **query: str | int) -> httpx.Response:
        """クエリ: `source_id`・`status`(`active` を含む)・`page`・`items_per_page`・`sort`。"""
        return self._client.get(f"{ADMIN_API_PREFIX}/jobs", params=query)

    def get_job(self, job_id: str) -> httpx.Response:
        return self._client.get(f"{ADMIN_API_PREFIX}/jobs/{job_id}")

    # --- documents・opensearch・dashboard・meta(EP-11〜14) ---

    def list_documents(self, source_id: str, **query: str | int) -> httpx.Response:
        """クエリ: `tab`・`page`・`items_per_page`・`sort`。"""
        return self._client.get(f"{ADMIN_API_PREFIX}/sources/{source_id}/documents", params=query)

    def opensearch_cluster(self) -> httpx.Response:
        return self._client.get(f"{ADMIN_API_PREFIX}/opensearch/cluster")

    def dashboard(self) -> httpx.Response:
        return self._client.get(f"{ADMIN_API_PREFIX}/dashboard")

    def meta(self) -> httpx.Response:
        return self._client.get(f"{ADMIN_API_PREFIX}/meta")


# --- OpenSearch の直接検証 ---


class OpenSearchProbe:
    """OpenSearch の REST API を直接**読む**検証用クライアント(opensearch-py は使わない)。

    Admin API が読んだ実データを、api を経由せずに読んで、独立に計算した期待値と照合するために使う。
    書き込みは、実 Crawler に作らせられない前提(スキップ記録・孤児ロック)の 2 つだけ(`write_*`)。
    検索・件数の確認の前には必ず `_refresh` する(refresh 前は新しい書き込みが見えないため)。
    ID 指定の取得(GET)は refresh なしで最新が読める。
    """

    # `search` の 1 回の取得上限(件)。テストのデータは、これより十分少ない。
    SEARCH_PAGE_SIZE = 100

    def __init__(self, base_url: str) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=30.0)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "OpenSearchProbe":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        return self._http.request(method, path, **kwargs)

    def refresh(self, index: str) -> None:
        response = self._http.post(f"/{index}/_refresh")
        assert response.status_code == 200, f"refresh {index} failed: {response.text[:300]}"

    def search(
        self, index: str, query: dict[str, Any], *, size: int = SEARCH_PAGE_SIZE
    ) -> list[dict[str, Any]]:
        self.refresh(index)
        response = self._http.post(f"/{index}/_search", json={"query": query, "size": size})
        assert response.status_code == 200, f"search {index} failed: {response.text[:300]}"
        return list(response.json()["hits"]["hits"])

    def count(self, index: str, query: dict[str, Any]) -> int:
        self.refresh(index)
        response = self._http.post(f"/{index}/_count", json={"query": query})
        assert response.status_code == 200, f"count {index} failed: {response.text[:300]}"
        return int(response.json()["count"])

    def fetch(self, index: str, record_id: str) -> dict[str, Any] | None:
        """ID で 1 件取得する。なければ None。返すのは `_source` などを含む応答本文。"""
        response = self._http.get(f"/{index}/_doc/{record_id}")
        if response.status_code == 404 and response.json().get("found") is False:
            return None
        assert response.status_code == 200, f"get {index}/{record_id} failed: {response.text[:300]}"
        return dict(response.json())

    def fetch_source(self, index: str, record_id: str) -> dict[str, Any] | None:
        record = self.fetch(index, record_id)
        return None if record is None else dict(record["_source"])

    # --- 検索インデックス(文書) ---

    def source_documents(self, source_id: str) -> list[dict[str, Any]]:
        """`source_id` の索引済み文書(`_id` は `document_id`)。"""
        return self.search(SEARCH_INDEX, {"term": {"source_id": source_id}})

    def count_source_documents(self, source_id: str) -> int:
        return self.count(SEARCH_INDEX, {"term": {"source_id": source_id}})

    # --- loreley-jobs(ジョブ・ロック・スキップ記録・原本サイズ超過記録・メンテナンスフラグ) ---

    def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        return self.fetch_source(JOBS_INDEX, job_id)

    def fetch_lock(self, source_id: str) -> dict[str, Any] | None:
        return self.fetch_source(JOBS_INDEX, f"lock-{source_id}")

    def job_records_of(self, source_id: str) -> list[dict[str, Any]]:
        query = {
            "bool": {
                "filter": [{"term": {"record_type": "job"}}, {"term": {"source_id": source_id}}]
            }
        }
        return self.search(JOBS_INDEX, query)

    def oversize_records(self, source_id: str) -> list[dict[str, Any]]:
        """`source_id` の原本サイズ超過記録(ID は `oversize-{source_id}-{document_id}`)。"""
        query = {
            "bool": {
                "filter": [
                    {"term": {"record_type": "oversize"}},
                    {"term": {"source_id": source_id}},
                ]
            }
        }
        return self.search(JOBS_INDEX, query)

    def maintenance_flag_exists(self) -> bool:
        return self.fetch(JOBS_INDEX, MAINTENANCE_RECORD_ID) is not None

    # --- loreley-deletions(Indexer の削除結果) ---

    def fetch_deletion_result(self, job_id: str) -> dict[str, Any] | None:
        """Indexer の削除結果 `deletion_result-{crawl_id}`。Crawler のジョブ ID が `crawl_id`。"""
        return self.fetch_source(DELETIONS_INDEX, f"deletion_result-{job_id}")

    # --- loreley-sources(データソース設定) ---

    def fetch_source_config(self, source_id: str) -> dict[str, Any] | None:
        return self.fetch_source(SOURCES_INDEX, source_id)

    def source_config_records(self) -> list[dict[str, Any]]:
        """登録済みのデータソース設定の全件(`_id`=`source_id` の昇順。検索結果の形)。"""
        hits = self.search(SOURCES_INDEX, {"match_all": {}})
        assert len(hits) < self.SEARCH_PAGE_SIZE, (
            f"{len(hits)} sources reach the search limit {self.SEARCH_PAGE_SIZE}; "
            "the independent computation would skip some of them"
        )
        return sorted(hits, key=lambda hit: hit["_id"])

    # --- クラスタ(EP-12 の独立した期待値。api と同じ引数で `_cat/*`・`_cluster/health` を読む) ---

    def cluster_health(self) -> dict[str, Any]:
        response = self._http.get("/_cluster/health")
        assert response.status_code == 200, f"cluster health failed: {response.text[:300]}"
        return dict(response.json())

    def cat_rows(self, kind: str, columns: str, **extra_params: str) -> list[dict[str, Any]]:
        """`_cat/{kind}`(indices・shards・nodes)の行。値は文字列のまま(api と同じく JSON 形式)。"""
        response = self._http.get(
            f"/_cat/{kind}",
            params={"format": "json", "h": columns, "bytes": "b", **extra_params},
        )
        assert response.status_code == 200, f"cat {kind} failed: {response.text[:300]}"
        return list(response.json())

    # --- 前提作りのための直接書き込み ---
    # 検索インデックス・`loreley-jobs` の書き込み手は本来 Indexer・Crawler だけ(admin-api 1.1)。
    # 次の 2 つは、実 Crawler に作らせられない状態を作るための前提作りだけで、判定は Admin API と
    # 実 Crawler の応答で行う(Crawler の結合テストの `force_last_seen_at` が前例)。形式は
    # crawler-architecture 3.3.3・5.1 と、実 Crawler が書いた実物の記録に合わせる。

    def write_skip_record(
        self,
        *,
        source_id: str,
        document_id: str,
        external_id: str,
        stage: str,
        reason: str,
        attempts: int,
        consecutive_skips: int,
        first_skipped_at: datetime,
        last_skipped_at: datetime,
        last_job_id: str,
    ) -> None:
        """スキップ記録 `skip-{source_id}-{document_id}`(crawler-architecture 3.3.3)を作る。

        実 Crawler がスキップを記録するには、取得の失敗(権限エラーなど)を起こす必要がある。
        macOS の bind mount で確実に起こせないため、記録だけを直接書く(AIT-41)。
        """
        self._create_job_index_record(
            f"skip-{source_id}-{document_id}",
            {
                "record_type": "skip",
                "source_id": source_id,
                "document_id": document_id,
                "external_id": external_id,
                "stage": stage,
                "reason": reason,
                "attempts": attempts,
                "consecutive_skips": consecutive_skips,
                "first_skipped_at": format_instant(first_skipped_at),
                "last_skipped_at": format_instant(last_skipped_at),
                "last_job_id": last_job_id,
            },
        )

    def write_lock_record(
        self,
        *,
        source_id: str,
        owner: str,
        job_id: str,
        acquired_at: datetime,
        lease_expires_at: datetime,
        heartbeat_at: datetime,
    ) -> None:
        """ロック文書 `lock-{source_id}`(crawler-architecture 5.1)を作る。

        孤児ロック(ジョブが終端なのにロックだけが残る状態)は、Crawler の異常終了などでしか生じない。
        Crawler は起動時の回復で自分のロックを消すため、実 Crawler には作らせられない(AIT-51)。
        """
        self._create_job_index_record(
            f"lock-{source_id}",
            {
                "record_type": "lock",
                "source_id": source_id,
                "owner": owner,
                "job_id": job_id,
                "lease_expires_at": format_instant(lease_expires_at),
                "heartbeat_at": format_instant(heartbeat_at),
                "acquired_at": format_instant(acquired_at),
            },
        )

    def _create_job_index_record(self, record_id: str, body: dict[str, Any]) -> None:
        """`loreley-jobs` に作る(あれば失敗する。`source_id` は一意なので衝突しない)。"""
        response = self._http.put(
            f"/{JOBS_INDEX}/_create/{record_id}", params={"refresh": "true"}, json=body
        )
        assert response.status_code == 201, f"create {record_id} failed: {response.text[:300]}"


# --- 検索対象のディレクトリ ---


@dataclass(frozen=True)
class SourceDirectory:
    """データソース 1 つ分の検索対象ディレクトリ(ホストの `data/<source_id>/`)。

    Crawler には `DOCUMENTS_DIR` が `/data/documents` に `:ro` で mount されているので、ホスト側に
    置いたファイルが、コンテナ内の `container_root` から見える。Crawler は uid 10001 で動き、
    ホストの所有者と異なるため、ファイルは 0644、ディレクトリは 0755(others が読める)にする。
    """

    source_id: str

    @property
    def host_path(self) -> Path:
        return DOCUMENTS_DIR / self.source_id

    @property
    def container_root(self) -> str:
        """データソース設定の `connector_config.root` に書く、コンテナ内のパス。"""
        return f"{CONTAINER_DOCUMENTS_ROOT}/{self.source_id}"

    def create(self) -> None:
        self._make_directory(self.host_path)

    def write(self, relative_path: str, content: bytes) -> None:
        """ファイルを置く(あれば上書き)。親ディレクトリは 0755 で作る。"""
        path = self.host_path / relative_path
        self._make_directory(path.parent)
        path.write_bytes(content)
        path.chmod(0o644)

    def remove(self, relative_path: str) -> None:
        (self.host_path / relative_path).unlink()

    def cleanup(self) -> None:
        shutil.rmtree(self.host_path, ignore_errors=True)

    def document_id_of(self, relative_path: str) -> str:
        return compute_document_id(self.source_id, relative_path)

    @staticmethod
    def _make_directory(path: Path) -> None:
        # umask に依らず 0755 にするため、作った後に chmod する(`mkdir(mode=)` は umask の
        # 影響を受ける)。`data/` 自体と、その下の中間ディレクトリのどれもが、others に読めて入れる
        # 必要がある。
        missing = [directory for directory in [path, *path.parents] if not directory.exists()]
        path.mkdir(parents=True, exist_ok=True)
        for directory in missing:
            directory.chmod(0o755)


# --- データソース設定 ---

# 既定の設定。ttl は短く(10 分)、割合ルールは削除を妨げない値にする(AIT-21 など、削除を確認する
# テストは、必要な項目だけ上書きする)。
DEFAULT_TTL_SECONDS = 600
DEFAULT_RATIO_THRESHOLD_PERCENT = 50
DEFAULT_MIN_DELETE_COUNT = 0


def source_settings(directory: SourceDirectory, **overrides: Any) -> dict[str, Any]:
    """EP-03 `POST /sources` の本文。`root` はコンテナ内のパス。"""
    body: dict[str, Any] = {
        "source_id": directory.source_id,
        "connector_type": "file_system",
        "connector_config": {"root": directory.container_root},
        "ttl_seconds": DEFAULT_TTL_SECONDS,
        "ratio_threshold_percent": DEFAULT_RATIO_THRESHOLD_PERCENT,
        "min_delete_count": DEFAULT_MIN_DELETE_COUNT,
    }
    body.update(overrides)
    return body


def register_source(api: AdminApi, directory: SourceDirectory, **overrides: Any) -> dict[str, Any]:
    """データソースを EP-03 で登録し、201 を確認する。応答本文(保存された設定)を返す。"""
    return dict(expect_json(api.register_source(source_settings(directory, **overrides)), 201))


def run_crawl(
    api: AdminApi,
    opensearch: OpenSearchProbe,
    source_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """EP-06 でクロールを起動し、`succeeded` で終わり、ロックが解放されるまで待つ。

    EP-10 のジョブ詳細を返す。`succeeded` 以外で終わったときは、原因が分かるよう理由つきで失敗させる
    (クロールの失敗を確かめるテストは、これを使わず自分で待つ)。
    """
    accepted = expect_json(api.start_crawl(source_id, body), 202)
    job = wait_for_job_terminal(api, accepted["job_id"])
    assert job["status"] == "succeeded", (
        f"the crawl of {source_id} must succeed: status={job['status']} "
        f"failure_reason={job['failure_reason']} failure_detail={job['failure_detail']}"
    )
    wait_for_lock_released(opensearch, source_id)
    return job


# --- 障害系: コンポーネントの停止と起動 ---

COMPOSE_PROJECT_NAME = "loreley-it"
COMPOSE_FILES = (
    REPOSITORY_ROOT / "deploy/compose/compose.yaml",
    REPOSITORY_ROOT / "tests/integration/api/compose.test.yaml",
)
# 障害系が止めてよいサービス。api は止めない(テストの対象)。opensearch-init は使い捨て。
CONTROLLABLE_SERVICES = frozenset({"crawler", "indexer", "opensearch"})
CONTROLLABLE_ACTIONS = frozenset({"stop", "start"})
# 障害系を許可する環境変数。スクリプトが export する(手動で pytest を直接実行したときに、意図せず
# コンテナを止めないため)。
ALLOW_COMPOSE_CONTROL_ENV = "LORELEY_IT_ALLOW_COMPOSE_CONTROL"
COMPOSE_COMMAND_TIMEOUT_SECONDS = 120.0
DOCKER_INSPECT_TIMEOUT_SECONDS = 30.0


def is_compose_control_allowed() -> bool:
    return os.environ.get(ALLOW_COMPOSE_CONTROL_ENV) == "1"


def _compose_base_command() -> list[str]:
    """プロジェクト名と compose ファイルを固定した `docker compose` の前半(常にこの 2 つだけ)。"""
    command = ["docker", "compose", "-p", COMPOSE_PROJECT_NAME]
    for compose_file in COMPOSE_FILES:
        command += ["-f", str(compose_file)]
    return command


def build_compose_command(action: str, service: str) -> list[str]:
    """`docker compose stop|start <service>` の引数リスト。プロジェクトと許可リストを固定する。

    shell を介さず引数リストで実行する。許可リストにない操作・サービスは、組み立て前に拒否する。
    """
    if action not in CONTROLLABLE_ACTIONS:
        raise ValueError(
            f"compose action {action!r} is not allowed: {sorted(CONTROLLABLE_ACTIONS)}"
        )
    if service not in CONTROLLABLE_SERVICES:
        raise ValueError(
            f"compose service {service!r} is not allowed: {sorted(CONTROLLABLE_SERVICES)}"
        )
    return [*_compose_base_command(), action, service]


class ComposeControl:
    """障害系のテストが、`loreley-it` のサービスを止めて起動し、healthy まで待つ。

    操作できるのはプロジェクト `loreley-it` の `crawler`・`indexer`・`opensearch` の `stop`・`start`
    だけ(`build_compose_command`)。開発用スタックや他のプロジェクトのコンテナには触れない。
    テストは、止めたら必ず `finally` で `start` し、`wait_healthy` で戻るのを確認する。
    """

    def stop(self, service: str) -> None:
        self._run(build_compose_command("stop", service), service)

    def start(self, service: str) -> None:
        self._run(build_compose_command("start", service), service)

    def wait_healthy(
        self, service: str, *, timeout_secs: float = SERVICE_RECOVERY_TIMEOUT_SECONDS
    ) -> None:
        """コンテナが running かつ healthcheck が healthy になるのを待つ(上限つき)。"""
        poll_until(
            lambda: self._container_state(service),
            lambda state: state == "running healthy",
            timeout_secs=timeout_secs,
            poll_interval_secs=SERVICE_RECOVERY_POLL_INTERVAL_SECONDS,
            what=f"{service} becoming healthy",
        )

    def _run(self, command: list[str], service: str) -> None:
        # 操作の前に、プロジェクトにコンテナが実在することを確認する(別の名前を指す事故を避ける)。
        self._container_id(service)
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=self._environment(),
            capture_output=True,
            text=True,
            timeout=COMPOSE_COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
        assert result.returncode == 0, (
            f"{' '.join(command[-2:])} failed ({result.returncode}): {result.stderr[-500:]}"
        )

    def _container_id(self, service: str) -> str:
        result = subprocess.run(
            [*_compose_base_command(), "ps", "-aq", service],
            cwd=REPOSITORY_ROOT,
            env=self._environment(),
            capture_output=True,
            text=True,
            timeout=DOCKER_INSPECT_TIMEOUT_SECONDS,
            check=False,
        )
        container_id = result.stdout.strip()
        assert result.returncode == 0 and container_id, (
            f"{service} has no container in project {COMPOSE_PROJECT_NAME}: "
            f"rc={result.returncode} {result.stderr[-300:]}"
        )
        return container_id

    def _container_state(self, service: str) -> str:
        """`<running|exited|...> <healthy|unhealthy|starting|none>`(healthcheck なしは none)。"""
        template = (
            "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
        )
        result = subprocess.run(
            ["docker", "inspect", "-f", template, self._container_id(service)],
            capture_output=True,
            text=True,
            timeout=DOCKER_INSPECT_TIMEOUT_SECONDS,
            check=False,
        )
        return result.stdout.strip() or f"inspect failed: {result.stderr.strip()}"

    @staticmethod
    def _environment() -> dict[str, str]:
        # compose は全サービスを解釈するので、検索対象の mount 元の変数が空だと既定値で解釈される。
        # 値は stop・start・ps の結果に影響しないが、スクリプトと同じ値にそろえる。
        return {**os.environ, "CRAWLER_DOCUMENTS_DIR": str(DOCUMENTS_DIR)}

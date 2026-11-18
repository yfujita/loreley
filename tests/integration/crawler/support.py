"""結合テストの共通部品(テストから import して使う。pytest のフィクスチャは conftest.py)。

含むもの:
  - 接続先・索引名・待ちの上限などの定数
  - `document_id` の**独立実装**(Crawler・Indexer のコードは import しない。実装の誤りを
    テストが同じ誤りで見逃さないため)
  - OpenSearch を直接読み書きする検証ヘルパ(`OpenSearchProbe`)
  - Crawler の HTTP API のクライアント(`CrawlerApi`)と、ジョブの完了待ち
  - 検索対象のディレクトリを `source_id` ごとに作る `SourceDirectory`

設計上の位置づけ:
  Crawler にはジョブの状態を取得する API がない(ジョブ状態・削除結果は Admin API が OpenSearch を
  直接読む設計。crawler-api 1 章)。そのため、判定は Crawler の HTTP 応答と、OpenSearch の実データ
  (`loreley-jobs`・`loreley-deletions`・検索インデックス・`loreley-sources`)の両方で行う。
"""

import hashlib
import os
import re
import shutil
import time
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

# --- 接続先(compose が 127.0.0.1 だけに publish したポート。環境変数で上書きできる) ---
CRAWLER_URL = os.environ.get("LORELEY_IT_CRAWLER_URL", "http://127.0.0.1:8001")
INDEXER_URL = os.environ.get("LORELEY_IT_INDEXER_URL", "http://127.0.0.1:8000")
OPENSEARCH_URL = os.environ.get("LORELEY_IT_OPENSEARCH_URL", "http://127.0.0.1:9200")

# --- 索引名(compose の既定。検索インデックスはエイリアス。infra/opensearch の init が作る) ---
SEARCH_INDEX = "loreley-documents"
DELETIONS_INDEX = "loreley-deletions"
JOBS_INDEX = "loreley-jobs"
SOURCES_INDEX = "loreley-sources"
MAINTENANCE_RECORD_ID = "maintenance"

# --- 検索対象のディレクトリ ---
# ホスト側は compose の `CRAWLER_DOCUMENTS_DIR`(スクリプトが export する)と同じ場所。
# Crawler はこれを `:ro` で `/data/documents` に mount している。
SAMPLES_DIR = Path(__file__).parent / "samples"
DOCUMENTS_DIR = Path(os.environ.get("CRAWLER_DOCUMENTS_DIR") or Path(__file__).parent / "data")
CONTAINER_DOCUMENTS_ROOT = "/data/documents"

# compose.yaml の LORELEY_CRAWLER_OWNER。ロック文書の `owner` で検証する。
CRAWLER_OWNER = "crawler-1"

# `OpenSearchProbe.search` の 1 回の取得上限(件)。テストのデータは、これより十分少ない。
SEARCH_PAGE_SIZE = 100

# compose.test.yaml の MAX_RAW_BYTES(65,536)を超える原本のサイズ。
# この値は compose.test.yaml の MAX_RAW_BYTES=65536 が前提(変えるときは両方を確認する)。
OVERSIZE_RAW_BYTES = 70_000

# --- データソース設定の既定値 ---
# ttl は短く(10 分)、割合ルールは削除を妨げない値(`min_delete_count=0`、
# `ratio_threshold=0.5`)にする。TTL 削除のテスト(CIT-30)で、削除の割合(T/D = 2/6)が
# 閾値以下になる前提を作るため。
TTL_SECONDS = 600
RATIO_THRESHOLD = 0.5
MIN_DELETE_COUNT = 0
# `last_seen_at` を過去に書き換えるときの経過時間。ttl(10 分)を大きく過ぎ、数分の時計のずれでも
# 期限の境界に近づかない。
EXPIRED_AGE = timedelta(hours=2)

# --- 待ち(間隔と上限を明示する。上限を超えたら、最後の状態つきで失敗させる) ---
# ジョブの完了。compose.test.yaml の削除結果のポーリング上限(120 秒)より短くし、Crawler の失敗で
# ジョブが居座ったときは、Crawler 側の打ち切りより先にテストが原因つきで失敗する。
JOB_WAIT_TIMEOUT_SECONDS = 90.0
JOB_POLL_INTERVAL_SECONDS = 0.5
# ロックの観測。ロックが存在する時間の窓は、削除結果のポーリング間隔(compose.test.yaml で 2 秒)が
# 決める。
LOCK_WAIT_TIMEOUT_SECONDS = 30.0
LOCK_POLL_INTERVAL_SECONDS = 0.2

TERMINAL_JOB_STATUSES = frozenset({"succeeded", "partially_succeeded", "failed", "cancelled"})


# --- 時刻 ---


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(instant: datetime) -> str:
    """UTC・ISO 8601・ミリ秒精度の文字列(例 `2026-11-09T01:00:00.000Z`)。"""
    utc_instant = instant.astimezone(UTC)
    return utc_instant.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_instant.microsecond // 1000:03d}Z"


def parse_instant(value: str) -> datetime:
    return datetime.fromisoformat(value)


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


# --- 応答の検査 ---


def expect_json(response: httpx.Response, expected_status: int) -> Any:
    """ステータスコードを検査して、JSON を返す。違えば、応答本文つきで失敗させる。"""
    assert response.status_code == expected_status, (
        f"{response.request.method} {response.request.url.path} returned "
        f"{response.status_code} (expected {expected_status}): {response.text[:500]}"
    )
    return response.json()


def expect_error(response: httpx.Response, expected_status: int, expected_code: str) -> None:
    """共通のエラー形式(crawler-api 3.3。`error` に `code`・`message`・`retryable`)を検査する。"""
    body = expect_json(response, expected_status)
    error = body.get("error")
    assert isinstance(error, dict), f"the error body must have an 'error' object: {body}"
    assert error.get("code") == expected_code, f"error code must be {expected_code}: {body}"
    assert set(error) >= {"code", "message", "retryable"}, f"error must have the 3 keys: {body}"


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


# --- OpenSearch の直接検証 ---


class OpenSearchProbe:
    """OpenSearch の REST API を直接呼ぶ検証用クライアント(opensearch-py は使わない)。

    Crawler・Indexer が書いた実データを、それらを経由せずに読んで確かめるために使う。
    検索・件数の確認の前には必ず `_refresh` する(refresh 前は新しい書き込みが見えないため)。
    ID 指定の取得(GET)は refresh なしで最新が読める。
    """

    def __init__(self, base_url: str) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=30.0)

    def close(self) -> None:
        self._http.close()

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

    def source_document_ids(self, source_id: str) -> set[str]:
        return {hit["_id"] for hit in self.source_documents(source_id)}

    def count_source_documents(self, source_id: str) -> int:
        return self.count(SEARCH_INDEX, {"term": {"source_id": source_id}})

    def fetch_document(self, source_id: str, external_id: str) -> dict[str, Any] | None:
        return self.fetch_source(SEARCH_INDEX, compute_document_id(source_id, external_id))

    def search_content(self, source_id: str, text: str) -> list[dict[str, Any]]:
        """`source_id` の文書のうち、本文(`content`)が語 `text` に一致するものを検索する。"""
        query = {
            "bool": {
                "filter": [{"term": {"source_id": source_id}}],
                "must": [{"match": {"content": text}}],
            }
        }
        return self.search(SEARCH_INDEX, query)

    def force_last_seen_at(self, source_id: str, value: datetime) -> int:
        """**テストの前提を作るための直接書き込み**。全文書の `last_seen_at` を `value` にする。

        TTL 削除のテスト(CIT-30)で、「前回のクロールで見た文書が期限切れになっている」状態を、
        実時間で待たずに作る。Crawler は `crawl_started_at` を自分の時計で決めるので、テストから
        クロールの時刻を過去にできない。検索インデックスへの書き込みは本来 Indexer だけが行う
        (api 3.1)ので、使うのは前提作りだけ(Indexer の結合テストの `force_last_seen_at` と
        同じ前例)。更新した件数を返す。
        """
        hits = self.source_documents(source_id)
        # search の取得上限で黙って打ち切ると、書き換え漏れが「削除されない文書」に見える。
        assert len(hits) < SEARCH_PAGE_SIZE, (
            f"{source_id} has {len(hits)} documents, at or over the search limit "
            f"{SEARCH_PAGE_SIZE}; force_last_seen_at would skip some of them"
        )
        document_ids = sorted(hit["_id"] for hit in hits)
        for document_id in document_ids:
            response = self._http.post(
                f"/{SEARCH_INDEX}/_update/{document_id}",
                params={"refresh": "true"},
                json={"doc": {"last_seen_at": iso(value)}},
            )
            assert response.status_code == 200, f"force last_seen_at failed: {response.text[:300]}"
        return len(document_ids)

    # --- loreley-jobs(ジョブ・ロック・スキップ記録・原本サイズ超過記録・メンテナンスフラグ) ---

    def fetch_job(self, job_id: str) -> dict[str, Any] | None:
        return self.fetch_source(JOBS_INDEX, job_id)

    def fetch_lock(self, source_id: str) -> dict[str, Any] | None:
        return self.fetch_source(JOBS_INDEX, f"lock-{source_id}")

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

    def job_records_of(self, source_id: str) -> list[dict[str, Any]]:
        query = {
            "bool": {
                "filter": [{"term": {"record_type": "job"}}, {"term": {"source_id": source_id}}]
            }
        }
        return self.search(JOBS_INDEX, query)

    def set_maintenance_flag(self, *, enabled: bool) -> None:
        """メンテナンスフラグ(`loreley-jobs` の ID `maintenance`)を書く(運用者と同じ形式)。"""
        response = self._http.put(
            f"/{JOBS_INDEX}/_doc/{MAINTENANCE_RECORD_ID}",
            params={"refresh": "true"},
            json={"record_type": "maintenance", "enabled": enabled},
        )
        assert response.status_code in (200, 201), f"set maintenance failed: {response.text[:300]}"

    def delete_maintenance_flag(self) -> None:
        response = self._http.delete(
            f"/{JOBS_INDEX}/_doc/{MAINTENANCE_RECORD_ID}", params={"refresh": "true"}
        )
        assert response.status_code in (200, 404), (
            f"delete maintenance failed: {response.text[:300]}"
        )

    # --- loreley-deletions(Indexer の削除結果) ---

    def fetch_deletion_result(self, job_id: str) -> dict[str, Any] | None:
        """Indexer の削除結果 `deletion_result-{crawl_id}`。Crawler のジョブ ID が `crawl_id`。"""
        return self.fetch_source(DELETIONS_INDEX, f"deletion_result-{job_id}")

    def deletion_records_of(self, source_id: str) -> list[dict[str, Any]]:
        return self.search(DELETIONS_INDEX, {"term": {"source_id": source_id}})

    # --- loreley-sources(データソース設定) ---

    def fetch_source_config(self, source_id: str) -> dict[str, Any] | None:
        return self.fetch_source(SOURCES_INDEX, source_id)


# --- Crawler の HTTP API ---


class CrawlerApi:
    """Crawler の HTTP API(crawler-api 4 章)のクライアント。応答は検査せず、そのまま返す。"""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def healthz(self) -> httpx.Response:
        return self._client.get("/healthz")

    def register_source(self, body: dict[str, Any]) -> httpx.Response:
        return self._client.post("/sources", json=body)

    def start_crawl(self, source_id: str) -> httpx.Response:
        return self._client.post(f"/sources/{source_id}/crawl-jobs")

    def start_source_delete(self, source_id: str) -> httpx.Response:
        return self._client.post(f"/sources/{source_id}/delete-jobs")


def source_settings(
    source_id: str, directory: "SourceDirectory", **overrides: Any
) -> dict[str, Any]:
    """`POST /sources` の本文。`connector_type` は `file_system`(`filesystem` は 400)。"""
    body: dict[str, Any] = {
        "source_id": source_id,
        "connector_type": "file_system",
        "connector_config": {"root": directory.container_root},
        "ttl": TTL_SECONDS,
        "ratio_threshold": RATIO_THRESHOLD,
        "min_delete_count": MIN_DELETE_COUNT,
    }
    body.update(overrides)
    return body


def register_source(
    api: CrawlerApi, directory: "SourceDirectory", **overrides: Any
) -> dict[str, Any]:
    """データソースを登録し、201 を確認する。保存された設定(応答本文)を返す。"""
    body = source_settings(directory.source_id, directory, **overrides)
    return dict(expect_json(api.register_source(body), 201))


def start_job_ok(response: httpx.Response, *, job_type: str, source_id: str) -> str:
    """ジョブ起動が 202 で、`queued` のジョブが返ったことを確認して、`job_id` を返す。"""
    body = expect_json(response, 202)
    assert body["job_type"] == job_type, f"job_type must be {job_type}: {body}"
    assert body["source_id"] == source_id, f"source_id must be {source_id}: {body}"
    assert body["status"] == "queued", f"a new job must be queued: {body}"
    assert body["trigger"] == "manual", f"a job started by the API must be manual: {body}"
    return str(body["job_id"])


def wait_for_job(opensearch: OpenSearchProbe, job_id: str) -> dict[str, Any]:
    """ジョブ記録(`loreley-jobs`)が終端状態になるのを待つ。ジョブ記録の `_source` を返す。

    Crawler にジョブ状態の取得 API はないので、OpenSearch の記録を読む(間隔 0.5 秒、上限 90 秒)。
    """

    def is_terminal(job: dict[str, Any] | None) -> bool:
        return job is not None and job.get("status") in TERMINAL_JOB_STATUSES

    job = poll_until(
        lambda: opensearch.fetch_job(job_id),
        is_terminal,
        timeout_secs=JOB_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs=JOB_POLL_INTERVAL_SECONDS,
        what=f"job {job_id} reaching a terminal state",
    )
    assert job is not None  # is_terminal が保証する(型の絞り込みのため)
    return job


def assert_job_succeeded(job: dict[str, Any]) -> None:
    """ジョブが `succeeded` であること。違えば、失敗の理由と警告を載せて失敗させる。"""
    assert job["status"] == "succeeded", (
        f"the job must succeed: status={job['status']}, "
        f"failure_reason={job.get('failure_reason')}, "
        f"failure_detail={job.get('failure_detail')}, warnings={job.get('warnings')}, "
        f"registration={job.get('registration')}"
    )


def run_crawl(api: CrawlerApi, opensearch: OpenSearchProbe, source_id: str) -> dict[str, Any]:
    """クロールを起動(202)し、`succeeded` まで待つ。ジョブ記録の `_source` を返す。"""
    job_id = start_job_ok(api.start_crawl(source_id), job_type="crawl", source_id=source_id)
    job = wait_for_job(opensearch, job_id)
    assert_job_succeeded(job)
    return job


def run_source_delete(
    api: CrawlerApi, opensearch: OpenSearchProbe, source_id: str
) -> dict[str, Any]:
    """ソース削除ジョブを起動(202)し、`succeeded` まで待つ。ジョブ記録の `_source` を返す。"""
    job_id = start_job_ok(
        api.start_source_delete(source_id), job_type="source_delete", source_id=source_id
    )
    job = wait_for_job(opensearch, job_id)
    assert_job_succeeded(job)
    return job


def wait_for_lock_released(opensearch: OpenSearchProbe, source_id: str) -> None:
    """ロック文書 `lock-{source_id}` が消えるのを待つ。

    ロックの解放は、ジョブ記録が終端になった**後**に Job Runner が行う(最終状態の記録の後。
    architecture 4.5)。ジョブの完了を確認した直後は、まだ残っていることがあるため、待つ。
    """
    poll_until(
        lambda: opensearch.fetch_lock(source_id),
        lambda lock: lock is None,
        timeout_secs=LOCK_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs=LOCK_POLL_INTERVAL_SECONDS,
        what=f"the lock of {source_id} being released",
    )


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

    def copy_sample(self, relative_path: str) -> None:
        """`samples/` のファイルを、同じ相対パスで置く(外部 ID は相対パスになる)。"""
        self.write(relative_path, (SAMPLES_DIR / relative_path).read_bytes())

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

    def external_id_to_document_id(self, relative_path: str) -> str:
        return compute_document_id(self.source_id, relative_path)

    @staticmethod
    def _make_directory(path: Path) -> None:
        # umask に依らず 0755 にするため、作った後に chmod する(`mkdir(mode=)` は umask の
        # 影響を受ける)。
        # `data/` 自体と、その下の中間ディレクトリのどれもが、others に読めて入れる必要がある。
        missing = [path, *path.parents]
        missing = [directory for directory in missing if not directory.exists()]
        path.mkdir(parents=True, exist_ok=True)
        for directory in missing:
            directory.chmod(0o755)

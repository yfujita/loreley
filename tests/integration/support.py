"""結合テストの共通部品(テストから import して使う。pytest のフィクスチャは conftest.py)。

含むもの:
  - 接続先と索引名の定数
  - 時刻ヘルパ(TTL の決定的な作り方。実時間では待たない)
  - `document_id` の**独立実装**(Indexer のコードは import しない。IT-02 で突き合わせる)
  - OpenSearch を直接読み書きする検証ヘルパ(`OpenSearchProbe`)
  - Crawler 役のクライアント(`CrawlerClient` と、1 回のクロールを表す `Crawl`)

設計上の位置づけ:
  結合テストは Crawler の代わりに Indexer の HTTP API を呼ぶ(api 2 章の呼び出し順)。
  Crawler が `loreley-jobs` に書くロック文書も、Crawler 役として OpenSearch へ直接書く
  (書き込み役の分担は api 3.1。`loreley-jobs` に書くのは Crawler だけ)。
  検証は Indexer の応答だけでなく、OpenSearch の実データを直接読んで行う(`OpenSearchProbe`)。
"""

import base64
import contextlib
import hashlib
import os
import re
import time
import unicodedata
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

# --- 接続先(compose が 127.0.0.1 だけに publish したポート。環境変数で上書きできる) ---
INDEXER_URL = os.environ.get("LORELEY_IT_INDEXER_URL", "http://127.0.0.1:8000")
OPENSEARCH_URL = os.environ.get("LORELEY_IT_OPENSEARCH_URL", "http://127.0.0.1:9200")

# --- 索引名(Indexer の既定の仮名。search-index はエイリアス。infra/opensearch の init が作る) ---
SEARCH_INDEX = "loreley-documents"
DELETIONS_INDEX = "loreley-deletions"
JOBS_INDEX = "loreley-jobs"

# --- TTL の決定的な作り方 ---
# 実時間で待たず、`crawl_started_at` を過去に置いて「期限切れ」と「期限内」を作る。
#   クロール A(古い): 現在の 2 時間前。ここでしか見ていない文書は、TTL 600 秒を大きく過ぎる。
#   クロール B(新しい): 現在の 1 分前。ここで見た文書は、TTL 600 秒の期限内。
# 数分のホスト・Docker VM の時計ずれがあっても、境界(10 分)に近づかない余裕がある。
EXPIRED_AGE = timedelta(hours=2)
RECENT_AGE = timedelta(minutes=1)
TTL_SECONDS = 600
# 「削除対象を作りたくない」クロール(クロール A の終了など)に使う長い TTL(1 日)。
LONG_TTL_SECONDS = 86_400

# 削除ワーカーの走査(compose.test.yaml で 1 秒間隔)を待つポーリング。
DELETION_WAIT_TIMEOUT_SECONDS = 30.0
DELETION_POLL_INTERVAL_SECONDS = 0.5

# リース期限切れのロックを作るときの「期限が過ぎてからの経過時間」。数分のホスト・Docker VM の
# 時計ずれがあっても、確実に期限切れと判定されるように、1 時間にしている。
EXPIRED_LEASE_AGE = timedelta(hours=1)

# compose.test.yaml の LORELEY_INDEXER_MAX_RAW_BYTES(65,536)を超える原本のサイズ。
OVERSIZE_RAW_BYTES = 70_000

SAMPLES_DIR = Path(__file__).parent / "samples"
SAMPLE_MIME_TYPES = {
    "sample.txt": "text/plain",
    "sample.md": "text/markdown",
    "sample.html": "text/html",
    "sample.pdf": "application/pdf",
    "corrupt.pdf": "application/pdf",
}


# --- 時刻 ---


def utc_now() -> datetime:
    """現在時刻(UTC、ミリ秒に切り捨て)。

    Indexer はミリ秒に正規化して保存する(api 3.6)。テスト側もミリ秒に揃えておくと、
    `iso()` の文字列が、リクエストの値と保存される値の両方にそのまま使える。
    """
    return truncate_to_millis(datetime.now(UTC))


def ago(*, hours: int = 0, minutes: int = 0) -> datetime:
    return utc_now() - timedelta(hours=hours, minutes=minutes)


def truncate_to_millis(instant: datetime) -> datetime:
    return instant.replace(microsecond=instant.microsecond // 1000 * 1000)


def iso(instant: datetime) -> str:
    """UTC・ISO 8601・ミリ秒精度の文字列(例 `2026-11-09T01:00:00.000Z`。api 3.6 の正規形)。"""
    utc_instant = truncate_to_millis(instant.astimezone(UTC))
    return utc_instant.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc_instant.microsecond // 1000:03d}Z"


JST = timezone(timedelta(hours=9))


def iso_in_jst(instant: datetime) -> str:
    """JST(+09:00)の ISO 8601 表記。マイクロ秒があればそのまま出す(正規化の確認用の入力形)。"""
    return instant.astimezone(JST).isoformat()


MILLIS_INSTANT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


# --- ID ---


def unique_id(prefix: str) -> str:
    """テストごとに一意な ID(`source_id`・`crawl_id`)。前のテストのデータと干渉しない。"""
    safe_prefix = re.sub(r"[^A-Za-z0-9]+", "-", prefix).strip("-").lower()[:40]
    return f"it-{safe_prefix}-{uuid.uuid4().hex[:10]}"


def compute_document_id(source_id: str, external_id: str) -> str:
    """`document_id` の独立実装。README 6 章・api 3.3 の規則をテスト側で書き直したもの。

    SHA-256(`source_id` + NUL + `external_id`) の小文字 16 進。`external_id` はハッシュの前に
    NFC へ正規化し、`\\` を `/` に統一する。先頭の `/` は除去せず、大文字小文字も区別する。
    Indexer のコードを import しないのは、実装の誤りをテストが同じ誤りで見逃さないため。
    """
    normalized = unicodedata.normalize("NFC", external_id).replace("\\", "/")
    return hashlib.sha256(f"{source_id}\0{normalized}".encode()).hexdigest()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- 登録する文書 ---


@dataclass(frozen=True)
class Lock:
    """ロック所有情報(api 3.2)。`job_id` は、通常はクロールの `crawl_id` と同じ。"""

    owner: str
    job_id: str

    def as_body(self) -> dict[str, str]:
        return {"owner": self.owner, "job_id": self.job_id}


@dataclass(frozen=True)
class SourceDocument:
    """Crawler が Indexer に渡す文書 1 件(api 4.3 の `documents[]` の要素)。"""

    external_id: str
    raw: bytes
    mime_type: str
    title: str
    url: str | None = None
    path: str | None = None
    source_updated_at: str = "2026-11-08T12:00:00Z"
    # 申告サイズ。None なら実際の長さ。「申告だけが上限を超える」ケースを作るときに指定する。
    declared_size: int | None = None

    @property
    def content_hash(self) -> str:
        """原本の SHA-256。Indexer は照合も再計算もせず、この値をそのまま保存する(api 4.3)。"""
        return sha256_hex(self.raw)

    def document_id(self, source_id: str) -> str:
        return compute_document_id(source_id, self.external_id)

    def with_raw(self, raw: bytes) -> "SourceDocument":
        """同じ文書(同じ ID)の原本だけを差し替える。「本文が変わった」を作る。"""
        return replace(self, raw=raw)

    def to_request(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "external_id": self.external_id,
            "title": self.title,
            "mime_type": self.mime_type,
            "raw_content": base64.b64encode(self.raw).decode("ascii"),
            "content_hash": self.content_hash,
            "source_updated_at": self.source_updated_at,
            "size": len(self.raw) if self.declared_size is None else self.declared_size,
        }
        if self.url is not None:
            body["url"] = self.url
        if self.path is not None:
            body["path"] = self.path
        return body


def read_sample(file_name: str) -> bytes:
    return (SAMPLES_DIR / file_name).read_bytes()


def sample_document(file_name: str, *, external_id: str | None = None) -> SourceDocument:
    """`samples/` の固定ファイルから文書を作る。`external_id` の既定は `docs/{ファイル名}`。"""
    return SourceDocument(
        external_id=external_id or f"docs/{file_name}",
        raw=read_sample(file_name),
        mime_type=SAMPLE_MIME_TYPES[file_name],
        title=file_name,
        url=f"https://docs.example.com/{file_name}",
        path=f"docs/{file_name}",
    )


def text_document(external_id: str, text: str) -> SourceDocument:
    """UTF-8 のテキスト文書。件数や本文の変更を手軽に作るために使う。"""
    return SourceDocument(
        external_id=external_id,
        raw=text.encode("utf-8"),
        mime_type="text/plain",
        title=external_id,
        url=f"https://docs.example.com/{external_id}",
        path=external_id,
    )


def oversize_document(external_id: str) -> SourceDocument:
    """原本が `MAX_RAW_BYTES`(compose.test.yaml で 64 KiB)を超える文書。"""
    return SourceDocument(
        external_id=external_id,
        raw=b"x" * OVERSIZE_RAW_BYTES,
        mime_type="text/plain",
        title=external_id,
    )


# --- 応答の検査 ---


def expect_json(response: httpx.Response, expected_status: int) -> Any:
    """ステータスコードを検査して、JSON を返す。違えば、応答本文つきで失敗させる。"""
    assert response.status_code == expected_status, (
        f"{response.request.method} {response.request.url.path} returned "
        f"{response.status_code} (expected {expected_status}): {response.text[:500]}"
    )
    return response.json()


def expect_error(response: httpx.Response, expected_status: int, expected_code: str) -> None:
    """共通のエラー形式 `{"error": {"code", "message", "retryable"}}`(api 3.4)を検査する。"""
    body = expect_json(response, expected_status)
    error = body.get("error")
    assert isinstance(error, dict), f"the error body must have an 'error' object: {body}"
    assert error.get("code") == expected_code, f"error code must be {expected_code}: {body}"
    assert set(error) >= {"code", "message", "retryable"}, f"error must have the 3 keys: {body}"


# --- OpenSearch の直接検証 ---


class OpenSearchProbe:
    """OpenSearch の REST API を直接呼ぶ検証用クライアント(opensearch-py は使わない)。

    Indexer が書いた実データを、Indexer を経由せずに読んで確かめるために使う。
    検索・件数の確認の前には必ず `_refresh` する(refresh 前は新しい書き込みが見えないため)。
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

    def count(self, index: str, query: dict[str, Any]) -> int:
        self.refresh(index)
        response = self._http.post(f"/{index}/_count", json={"query": query})
        assert response.status_code == 200, f"count {index} failed: {response.text[:300]}"
        return int(response.json()["count"])

    def count_without_refresh(self, index: str, query: dict[str, Any]) -> int:
        """`_refresh` せずに件数を数える。refresh されていない書き込みは数えられない。

        「検索可能でない状態を作れている」ことの確認に使う(`refresh_disabled` と組み合わせる)。
        """
        response = self._http.post(f"/{index}/_count", json={"query": query})
        assert response.status_code == 200, f"count {index} failed: {response.text[:300]}"
        return int(response.json()["count"])

    @contextlib.contextmanager
    def refresh_disabled(self, index: str) -> Iterator[None]:
        """`refresh_interval` を `-1`(自動 refresh なし)にして、終了時に既定へ戻す。

        書き込みが `_refresh` するまで検索できない状態を作り、Indexer が実行前に自分で refresh して
        いることを検出するために使う。元に戻す値は `null`(設定の削除=既定の 1 秒)。
        """
        self._put_refresh_interval(index, "-1")
        try:
            yield
        finally:
            self._put_refresh_interval(index, None)

    def _put_refresh_interval(self, index: str, value: str | None) -> None:
        response = self._http.put(
            f"/{index}/_settings", json={"index": {"refresh_interval": value}}
        )
        assert response.status_code == 200, f"set refresh_interval failed: {response.text[:300]}"

    def search_stats(self, index: str) -> dict[str, int]:
        """索引の検索の累計回数(`query_total`)と、スクロールの完了回数(`scroll_total`)。

        テストの前後の差分から、Indexer がその間に行った検索・`delete_by_query` の回数を見積もる
        (`_count`・`_search` は `query_total` に、`delete_by_query` の 1 回の実行は
        `scroll_total` に数えられる。GET による ID 取得は数えられない)。
        """
        response = self._http.get(f"/{index}/_stats/search")
        assert response.status_code == 200, f"stats {index} failed: {response.text[:300]}"
        search = response.json()["_all"]["primaries"]["search"]
        return {
            "query_total": int(search["query_total"]),
            "scroll_total": int(search["scroll_total"]),
        }

    def count_source_documents(self, source_id: str) -> int:
        return self.count(SEARCH_INDEX, {"term": {"source_id": source_id}})

    def search(self, index: str, query: dict[str, Any], *, size: int = 100) -> list[dict[str, Any]]:
        self.refresh(index)
        response = self._http.post(f"/{index}/_search", json={"query": query, "size": size})
        assert response.status_code == 200, f"search {index} failed: {response.text[:300]}"
        return list(response.json()["hits"]["hits"])

    def fetch(self, index: str, record_id: str) -> dict[str, Any] | None:
        """ID で 1 件取得する(GET は refresh なしで最新が読める)。なければ None。

        返すのは `_source`・`_seq_no`・`_primary_term` を含む応答本文。
        """
        response = self._http.get(f"/{index}/_doc/{record_id}")
        if response.status_code == 404 and response.json().get("found") is False:
            return None
        assert response.status_code == 200, f"get {index}/{record_id} failed: {response.text[:300]}"
        return dict(response.json())

    def fetch_source(self, index: str, record_id: str) -> dict[str, Any] | None:
        record = self.fetch(index, record_id)
        return None if record is None else dict(record["_source"])

    def fetch_document(self, source_id: str, external_id: str) -> dict[str, Any] | None:
        return self.fetch_document_by_id(compute_document_id(source_id, external_id))

    def fetch_document_by_id(self, document_id: str) -> dict[str, Any] | None:
        return self.fetch(SEARCH_INDEX, document_id)

    def write_lock_document(self, source_id: str, lock: Lock, lease_expires_at: datetime) -> None:
        """Crawler 役として、ロック文書 `lock-{source_id}` を `loreley-jobs` に書く。

        文書の形は README 6 章の仮定義(`owner`・`job_id`・`lease_expires_at`)。
        """
        response = self._http.put(
            f"/{JOBS_INDEX}/_doc/lock-{source_id}",
            params={"refresh": "true"},
            json={
                "owner": lock.owner,
                "job_id": lock.job_id,
                "lease_expires_at": iso(lease_expires_at),
            },
        )
        assert response.status_code in (200, 201), f"write lock failed: {response.text[:300]}"

    def delete_lock_document(self, source_id: str) -> None:
        """ロック文書を消す(「ロック文書がない」=所有していない、を作る)。"""
        response = self._http.delete(
            f"/{JOBS_INDEX}/_doc/lock-{source_id}", params={"refresh": "true"}
        )
        assert response.status_code in (200, 404), f"delete lock failed: {response.text[:300]}"

    def search_content(
        self, source_id: str, text: str, *, phrase: bool = False
    ) -> list[dict[str, Any]]:
        """`source_id` の文書のうち、本文(`content`)が `text` に一致するものを検索する。

        `phrase=True` なら語順どおりの連なり(match_phrase)、そうでなければ語の一致(match)。
        日本語は、アナライザなしの標準トークナイザで 1 文字ずつに分かれるため、
        `phrase=True` で探す。
        """
        clause = {"match_phrase" if phrase else "match": {"content": text}}
        query = {"bool": {"filter": [{"term": {"source_id": source_id}}], "must": [clause]}}
        return self.search(SEARCH_INDEX, query)

    def force_last_seen_at(self, source_id: str, external_id: str, value: datetime) -> None:
        """**テストの前提を作るための直接書き込み**。文書の `last_seen_at` を任意の値にする。

        通常の API の流れでは、受理中のクロールの `crawl_started_at` より新しい `last_seen_at` を
        持つ文書を作れない(世代の巻き戻りは `stale_crawl_started_at` で拒否されるため)。
        max 比較(古い値に戻らない)を確かめるために、実データを直接書き換えて用意する。
        検索インデックスへの書き込みは本来 Indexer だけが行う(api 3.1)ので、使うのは前提作りだけ。
        """
        document_id = compute_document_id(source_id, external_id)
        response = self._http.post(
            f"/{SEARCH_INDEX}/_update/{document_id}",
            params={"refresh": "true"},
            json={"doc": {"last_seen_at": iso(value)}},
        )
        assert response.status_code == 200, f"force last_seen_at failed: {response.text[:300]}"


# --- Crawler 役のクライアント ---


class CrawlerClient:
    """Indexer の HTTP API を Crawler として呼ぶ(api 4 章。応答は検査せず、そのまま返す)。"""

    def __init__(self, indexer: httpx.Client, opensearch: OpenSearchProbe) -> None:
        self._indexer = indexer
        self._opensearch = opensearch

    # 開始通知から終了通知までを 1 回のクロールとして扱う(`Crawl`)。
    def begin(
        self,
        source_id: str,
        *,
        started_at: datetime,
        ttl: int = LONG_TTL_SECONDS,
        ratio_threshold: float = 0.5,
        min_delete_count: int = 0,
        crawl_id: str | None = None,
        lease: timedelta = timedelta(hours=1),
        started_at_text: str | None = None,
    ) -> "Crawl":
        """ロックを取得(`loreley-jobs` に書き込み)して開始通知を送り、成功を確認する。

        api 2 章の手順 1「開始通知(ロック取得後・列挙前)」に当たる。
        `started_at_text` を指定すると、`crawl_started_at` をその表記で送る(秒精度・オフセット付き
        など、正規化の確認用)。`started_at` は、その表記が表す時刻のミリ秒切り捨て(期待値の算出用)。
        """
        resolved_crawl_id = crawl_id or unique_id("crawl")
        resolved_started_at_text = started_at_text or iso(started_at)
        lock = Lock(owner="it-crawler", job_id=resolved_crawl_id)
        self._opensearch.write_lock_document(source_id, lock, utc_now() + lease)
        response = self.start(
            {
                "crawl_id": resolved_crawl_id,
                "source_id": source_id,
                "crawl_started_at": resolved_started_at_text,
                "ttl": ttl,
                "ratio_threshold": ratio_threshold,
                "min_delete_count": min_delete_count,
            }
        )
        body = expect_json(response, 200)
        assert body == {"crawl_id": resolved_crawl_id, "status": "running"}, (
            f"the start notification must return the running crawl: {body}"
        )
        return Crawl(self, source_id, resolved_crawl_id, started_at, resolved_started_at_text, lock)

    def start(self, body: dict[str, Any]) -> httpx.Response:
        return self._indexer.post("/crawls/start", json=body)

    def finish(self, crawl_id: str, body: dict[str, Any]) -> httpx.Response:
        return self._indexer.post(f"/crawls/{crawl_id}/finish", json=body)

    def status(self, crawl_id: str) -> httpx.Response:
        return self._indexer.get(f"/crawls/{crawl_id}")

    def register(self, source_id: str, body: dict[str, Any]) -> httpx.Response:
        return self._indexer.post(f"/sources/{source_id}/documents:batch", json=body)

    def last_seen(self, source_id: str, body: dict[str, Any]) -> httpx.Response:
        return self._indexer.post(f"/sources/{source_id}/last-seen", json=body)

    def discard(self, source_id: str, lock: Lock) -> httpx.Response:
        """ソース削除 1(api 4.6)。"""
        body = {"lock": lock.as_body(), "reason": "source_deleted"}
        return self._indexer.post(f"/sources/{source_id}/deletions:discard", json=body)

    def delete_documents(self, source_id: str, lock: Lock) -> httpx.Response:
        """ソース削除 2(api 4.7)。`lock` は DELETE の JSON ボディで運ぶ(api 3.2)。"""
        return self._indexer.request(
            "DELETE", f"/sources/{source_id}/documents", json={"lock": lock.as_body()}
        )

    def delete_deletion_records(self, source_id: str, lock: Lock) -> httpx.Response:
        """ソース削除 3(api 4.8)。`lock` は DELETE の JSON ボディで運ぶ(api 3.2)。"""
        return self._indexer.request(
            "DELETE", f"/sources/{source_id}/deletion-records", json={"lock": lock.as_body()}
        )

    def wait_for_terminal(
        self,
        crawl_id: str,
        *,
        timeout_secs: float = DELETION_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs: float = DELETION_POLL_INTERVAL_SECONDS,
    ) -> dict[str, Any]:
        """Status API をポーリングして、削除結果が終端状態(`running` 以外)になるのを待つ。

        削除は終了通知のあと非同期に実行される(api 4.4)ため、ここだけは待ちが要る。
        間隔と上限を明示している。上限を超えたら、最後の状態つきで失敗させる。
        """
        deadline = time.monotonic() + timeout_secs
        last_body: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last_body = expect_json(self.status(crawl_id), 200)
            if last_body["status"] != "running":
                return last_body
            time.sleep(poll_interval_secs)
        raise AssertionError(
            f"the deletion result did not reach a terminal state within {timeout_secs}s "
            f"(polling every {poll_interval_secs}s): {last_body}"
        )


@dataclass(frozen=True)
class Crawl:
    """開始通知まで済んだ 1 回のクロール。登録・`last-seen`・終了通知を、この ID で送る。"""

    client: CrawlerClient
    source_id: str
    crawl_id: str
    started_at: datetime
    started_at_text: str  # リクエストに載せる `crawl_started_at` の表記
    lock: Lock

    def register(
        self, documents: list[SourceDocument], *, lock: Lock | None = None
    ) -> httpx.Response:
        """バッチ登録(api 4.3)。`lock` を指定すると、ロック不所有のケースを作れる。"""
        return self.client.register(
            self.source_id,
            {
                "crawl_id": self.crawl_id,
                "crawl_started_at": self.started_at_text,
                "lock": (lock or self.lock).as_body(),
                "documents": [document.to_request() for document in documents],
            },
        )

    def register_ok(self, documents: list[SourceDocument]) -> list[dict[str, Any]]:
        """バッチ登録が HTTP 200 で成功したことを確認して、文書単位の結果を返す。"""
        body = expect_json(self.register(documents), 200)
        results = list(body["results"])
        assert [r["external_id"] for r in results] == [d.external_id for d in documents], (
            f"results must come back in the request order: {results}"
        )
        return results

    def last_seen(self, document_ids: list[str], *, lock: Lock | None = None) -> httpx.Response:
        """`last_seen_at` の部分更新(api 4.2)。"""
        return self.client.last_seen(
            self.source_id,
            {
                "crawl_id": self.crawl_id,
                "crawl_started_at": self.started_at_text,
                "lock": (lock or self.lock).as_body(),
                "document_ids": document_ids,
            },
        )

    def last_seen_ok(self, document_ids: list[str]) -> list[dict[str, Any]]:
        body = expect_json(self.last_seen(document_ids), 200)
        return list(body["results"])

    def finish(
        self,
        *,
        enumerated_count: int,
        skipped_document_ids: list[str] | None = None,
        oversize_document_ids: list[str] | None = None,
        outcome: str = "enumeration_completed",
    ) -> httpx.Response:
        """終了通知(api 4.4)。`finished_at` は検証だけされ、保存されない。"""
        return self.client.finish(
            self.crawl_id,
            {
                "source_id": self.source_id,
                "outcome": outcome,
                "enumerated_count": enumerated_count,
                "skipped_document_ids": skipped_document_ids or [],
                "oversize_document_ids": oversize_document_ids or [],
                "finished_at": iso(utc_now()),
            },
        )

    def finish_and_wait(self, **kwargs: Any) -> dict[str, Any]:
        """終了通知を送り、202 を確認して、削除結果が終端状態になるまで待つ。"""
        response = self.finish(**kwargs)
        assert response.status_code == 202, f"finish must return 202: {response.status_code}"
        return self.client.wait_for_terminal(self.crawl_id)

    def status(self) -> dict[str, Any]:
        return dict(expect_json(self.client.status(self.crawl_id), 200))

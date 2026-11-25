"""AIT-30〜AIT-32: 実 OpenSearch に対する一覧・集計クエリの妥当性(EP-01・09・10・12)。

目的:
    Admin API が実 OpenSearch に発行するクエリ(`terms` 集計・`top_hits`・`bool` の絞り込み・`sort`・
    `from`/`size`・`cat.*`・`cluster.health`)が、実データに対して正しい結果を返すことを、テストが
    OpenSearch を**直接読んで独立に計算した期待値**と突き合わせて確かめる。
      - AIT-30: EP-01 の `last_crawl`・`last_completed_at`・`document_count` を、全ソースの全行で照合する
      - AIT-31: EP-09・10 の絞り込み・並べ替え・範囲外ページ・`window_limit`・`latest_for_source`
      - AIT-32: EP-12 を `_cat/*`・`_cluster/health` の直読みと照合する
    単体テストでは OpenSearch は fake で、クエリ本文の組み立てが実 OpenSearch で意図どおりに動くこと
    (集計の `size`、`top_hits` の並び、`sort` の同順位、`cat.*` の列)を確認できない。入力検証や
    `unavailable` の全分岐は単体テストで済んでおり、ここでは再検証しない。

参照する設計書の章:
    - admin-api-v0.1.md 2.1(ページング・同順位)、3.1(EP-01)、5.1・5.2(EP-09・10)、7.1(EP-12)
    - admin-api-architecture-v0.1.md の AAA-U-1(`terms` の `size`・`top_hits` の実機確認)

扱うシナリオ: AIT-30(EP-01 の全行照合)、AIT-31(EP-09・10)、AIT-32(EP-12)

検索で読む EP(EP-01・09・10 の `latest_for_source`)は、書き込みの反映が最大約 1 秒遅れる
(AAA-P-6)。期待値は、そのつど OpenSearch から読み直して再計算し、一致するまで上限つきで待つ
(アサートする値は曲げない)。

データについて:
    AIT-30・31 は、読み取りだけを行うので、モジュールで 1 回作った 3 つのソースを共有する
    (2 回クロール・1 回クロール・0 回クロール)。クロールの時間(1 回約 11 秒)を節約するため。
    AIT-30 は、登録ソースの総数が `terms` 集計の既定の `size`(10)を超えた状態を作るため、足りない分は
    クロールしない(登録だけの)ソースで補う。
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

from support import (
    DELETIONS_INDEX,
    EXPECTED_INDEX_NAMES,
    JOBS_INDEX,
    READ_LAG_POLL_INTERVAL_SECONDS,
    READ_LAG_TIMEOUT_SECONDS,
    SEARCH_INDEX,
    SOURCES_INDEX,
    TERMINAL_JOB_STATUSES,
    AdminApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_json,
    parse_instant,
    poll_until,
    register_source,
    run_crawl,
    unique_id,
    wait_for_job_list,
)

# EP-12 の `indices[]` の並び(状態の悪い順 → 名前の昇順。admin-api 7.1)。
_INDEX_STATUS_RANK = {"red": 0, "yellow": 1, "green": 2}
_SHARD_ROLE_BY_PRIREP = {"p": "primary", "r": "replica"}
_JOB_BRIEF_DATE_KEYS = ("queued_at", "started_at", "finished_at")
_COMPLETED_STATUSES = ("succeeded", "partially_succeeded")
# AIT-30 の時点の登録ソースの総数の下限。`terms` 集計の既定の `size`(10)を超え、`size` が足りないと
# 11 件目以降の行の値が欠ける(`last_crawl` が null・件数 0 になる)状態を作る。
MIN_REGISTERED_SOURCES = 12
TERMS_DEFAULT_SIZE = 10


@dataclass(frozen=True)
class CrawledSources:
    """AIT-30・31 が共有する、3 つのソース(読み取り専用)。"""

    crawled_twice: SourceDirectory
    first_job_id: str
    second_job_id: str
    crawled_twice_document_count: int
    crawled_once: SourceDirectory
    once_job_id: str
    crawled_once_document_count: int
    never_crawled: SourceDirectory


@pytest.fixture(scope="module")
def crawled_sources(api: AdminApi, opensearch: OpenSearchProbe) -> Iterator[CrawledSources]:
    """2 回・1 回・0 回クロールしたソースを作る(2 回目は md を 1 件足して、文書数を変える)。

    登録ソースの総数が `MIN_REGISTERED_SOURCES` に満たなければ、クロールしないソースを登録して補う
    (EP-01 の `terms` 集計が、既定の `size` を超える件数でも全行を返すことを AIT-30 が確かめるため)。
    """
    twice = SourceDirectory(unique_id("q-twice"))
    once = SourceDirectory(unique_id("q-once"))
    never = SourceDirectory(unique_id("q-never"))
    directories = (twice, once, never)
    try:
        for directory in directories:
            directory.create()
            register_source(api, directory)
        shortfall = MIN_REGISTERED_SOURCES - len(opensearch.source_config_records())
        for _ in range(max(shortfall, 0)):
            # クロールしないので、ディレクトリは作らない(ジョブも文書もない行になる)
            register_source(api, SourceDirectory(unique_id("q-registered-only")))
        twice.write("t1.md", b"# t1\n\ntext of t1\n")
        twice.write("t2.md", b"# t2\n\ntext of t2\n")
        once.write("o1.md", b"# o1\n\ntext of o1\n")
        once.write("o2.md", b"# o2\n\ntext of o2\n")

        first = run_crawl(api, opensearch, twice.source_id)
        twice.write("t3.md", b"# t3\n\ntext of t3\n")
        second = run_crawl(api, opensearch, twice.source_id)
        only = run_crawl(api, opensearch, once.source_id)
        yield CrawledSources(
            crawled_twice=twice,
            first_job_id=first["job_id"],
            second_job_id=second["job_id"],
            crawled_twice_document_count=3,
            crawled_once=once,
            once_job_id=only["job_id"],
            crawled_once_document_count=2,
            never_crawled=never,
        )
    finally:
        for directory in directories:
            directory.cleanup()


def test_source_listing_matches_the_rows_computed_independently_from_opensearch(
    api: AdminApi, opensearch: OpenSearchProbe, crawled_sources: CrawledSources
) -> None:
    """【何を確認するか】(AIT-30)
    EP-01 の全行の `last_crawl`・`last_completed_at`・`document_count`(・`delete_job`・`status`)が、
    OpenSearch を直接読んで独立に計算した値と一致すること。行は `source_id` の昇順で、このテストまでに
    作られた全ソースを含む。

    【前提と手順】
    前提: 2 回クロールしたソース(2 回目で文書が 3 件に増える)、1 回クロールしたソース、一度もクロール
    していないソースと、それまでのテストが作ったすべてのソース。登録ソースの総数は 12 件以上(足りない分は
    クロールしない登録だけのソース。`terms` の既定 `size` 10 を超える)。ジョブはすべて終端(conftest が待つ)。
    手順: EP-01 を呼ぶ。`loreley-sources`・`loreley-jobs`・検索インデックスを直接読んで行ごとの期待値を
    計算し、一致するまで(反映の遅れの分だけ)待つ。

    【期待する結果とその根拠】
    - 行ごとに、`last_crawl` は `queued_at` が最新の `crawl` ジョブ(同時刻は `job_id` 昇順)、
      `last_completed_at` は成功・一部成功の `crawl` ジョブの `finished_at` の最大値(なければ `null`)、
      `delete_job` は `deleting` のときだけ最新の `source_delete` ジョブ、`document_count` は検索インデックスの
      `source_id` 別の件数(0 件は 0)、`unavailable` は `{}`(B 3.1)。
    - 2 回クロールしたソース: `last_crawl` は 2 回目のジョブ(`terms` 集計の `top_hits` が最新を選ぶ)、
      `last_completed_at` はその `finished_at`、文書数は 3。1 回: そのジョブ、文書数 2。未クロール:
      `last_crawl`・`last_completed_at` は `null`、文書数 0。
    - 行数は 10 を超え(`terms` の既定 `size` を超える件数でも、全行が返る)、最上位の `unavailable` は `{}`。

    【単体テストでは確認できず実機で確認する点】
    実 OpenSearch での `terms` 集計の `size`(ソース数。10 を超える件数)・`top_hits` の並び・`max` 集計の
    値(エポックミリ秒から日時への変換)・件数の集計が、全行で独立計算と一致すること(AAA-U-1)。
    """

    def snapshot() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        listing = expect_json(api.list_sources(), 200)
        expected_rows = [
            _expected_source_row(opensearch, config)
            for config in opensearch.source_config_records()
        ]
        return [_listed_source_row(item) for item in listing["items"]], expected_rows, listing

    actual_rows, _, listing = poll_until(
        snapshot,
        lambda state: state[0] == state[1],
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what="EP-01 matching the rows computed from OpenSearch",
    )

    assert listing["unavailable"] == {}, f"the top-level unavailable must be empty: {listing}"
    # 全行が独立計算と一致しても、行数が `terms` の既定 size 以下では、size の不足を見逃す
    assert len(actual_rows) > TERMS_DEFAULT_SIZE, (
        f"more than {TERMS_DEFAULT_SIZE} sources must be listed to cover the terms size: "
        f"{len(actual_rows)}"
    )
    source_ids = [row["source_id"] for row in actual_rows]
    assert source_ids == sorted(source_ids), (
        f"EP-01 must list sources in ascending order: {source_ids}"
    )

    # 独立計算が両方とも空・同じ誤りでも通ってしまわないよう、3 つのソースの値そのものも確かめる。
    rows_by_id = {row["source_id"]: row for row in actual_rows}
    twice = rows_by_id[crawled_sources.crawled_twice.source_id]
    assert twice["last_crawl"]["job_id"] == crawled_sources.second_job_id, (
        f"last_crawl must be the second of the 2 crawls: {twice['last_crawl']}"
    )
    assert twice["last_completed_at"] == twice["last_crawl"]["finished_at"], (
        f"last_completed_at must be the finish time of the latest succeeded crawl: {twice}"
    )
    assert twice["document_count"] == crawled_sources.crawled_twice_document_count
    once = rows_by_id[crawled_sources.crawled_once.source_id]
    assert once["last_crawl"]["job_id"] == crawled_sources.once_job_id, f"last_crawl: {once}"
    assert once["document_count"] == crawled_sources.crawled_once_document_count
    never = rows_by_id[crawled_sources.never_crawled.source_id]
    assert (never["last_crawl"], never["last_completed_at"], never["delete_job"]) == (
        None,
        None,
        None,
    )
    assert never["document_count"] == 0, f"a never-crawled source has 0 documents: {never}"


def test_job_list_filters_sorts_pages_and_marks_the_latest_job(
    api: AdminApi, opensearch: OpenSearchProbe, crawled_sources: CrawledSources
) -> None:
    """【何を確認するか】(AIT-31)
    EP-09 の `source_id`・`status` の絞り込みと `total`、`sort`(`queued_at`・`-queued_at`)の順序、
    範囲外のページ、`window_limit`、登録されていないソースの空の結果が実 OpenSearch の検索で正しいこと。
    EP-10 の `latest_for_source` が、同じソースの古いジョブで `false`、最新のジョブで `true` になること。

    【前提と手順】
    前提: 2 回クロールしたソース(ジョブ 2 件、どちらも `succeeded`)、一度もクロールしていないソース。
    手順: EP-09 を `source_id`・`status`・`sort`・`page` を変えて呼ぶ。全ジョブの `total` は、
    `loreley-jobs` を直接数えた件数と比べる。EP-10 を 2 つのジョブで呼ぶ。

    【期待する結果とその根拠】
    - `source_id` で絞ると `total=2`。既定(`-queued_at`)は 2 回目 → 1 回目、`sort=-queued_at` も同じ、
      `sort=queued_at` は 1 回目 → 2 回目(B 2.1・5.1)。各行は `stalled=false`・`cancellable=false`・
      `unavailable={}`。応答は `page=1`・`items_per_page=25`・`window_limit=10000`・最上位 `unavailable={}`。
    - `status=succeeded` の絞り込みは 2 件、`status=failed`・`status=active` は 0 件。`status` のみ・
      無指定の `total` は、`loreley-jobs` の `record_type=job` の直接の件数(`status=succeeded` はその
      `succeeded` の件数)と一致する。
    - `page=2` は 200 で `items=[]`・`total=2`・`page=2`(範囲外のページはエラーにしない)。
    - 登録されていない `source_id`・未クロールの `source_id` は、404 でなく 200 の空(B 5.1)。
    - EP-10: 1 回目は `latest_for_source=false`、2 回目は `true`。どちらも成功なので `rerunnable=false`・
      `rerun_blocked_reason=not_failed`(B 2.9)。

    【単体テストでは確認できず実機で確認する点】
    実 OpenSearch の `term`・`terms` の絞り込み、`sort` の同順位、`from`/`size`、`track_total_hits`
    の `total`、最新ジョブの検索(`size: 1` + `sort`)の結果。
    """
    twice_id = crawled_sources.crawled_twice.source_id
    first_job_id = crawled_sources.first_job_id
    second_job_id = crawled_sources.second_job_id

    # source_id の絞り込みと並び(既定は -queued_at)
    newest_first = wait_for_job_list(
        api,
        lambda body: body["total"] == 2,
        what=f"EP-09 listing the 2 jobs of {twice_id}",
        source_id=twice_id,
    )
    assert [item["job_id"] for item in newest_first["items"]] == [second_job_id, first_job_id], (
        f"the default order must be newest first: {newest_first['items']}"
    )
    assert (
        newest_first["page"],
        newest_first["items_per_page"],
        newest_first["window_limit"],
        newest_first["unavailable"],
    ) == (1, 25, 10_000, {}), f"the paging fields must be echoed: {newest_first}"
    for item in newest_first["items"]:
        assert (item["status"], item["job_type"], item["source_id"]) == (
            "succeeded",
            "crawl",
            twice_id,
        ), f"a finished crawl of the source: {item}"
        assert (item["stalled"], item["cancellable"], item["unavailable"]) == (False, False, {}), (
            f"a finished job is neither stalled nor cancellable: {item}"
        )

    descending = wait_for_job_list(
        api,
        lambda body: [item["job_id"] for item in body["items"]] == [second_job_id, first_job_id],
        what="EP-09 listing the 2 jobs newest first with sort=-queued_at",
        source_id=twice_id,
        sort="-queued_at",
    )
    ascending = wait_for_job_list(
        api,
        lambda body: [item["job_id"] for item in body["items"]] == [first_job_id, second_job_id],
        what="EP-09 listing the 2 jobs oldest first with sort=queued_at",
        source_id=twice_id,
        sort="queued_at",
    )
    assert [item["job_id"] for item in descending["items"]] == [second_job_id, first_job_id]
    assert [item["job_id"] for item in ascending["items"]] == [first_job_id, second_job_id], (
        f"sort=queued_at must reverse the order: {ascending['items']}"
    )

    # status の絞り込み
    succeeded = wait_for_job_list(
        api,
        lambda body: body["total"] == 2,
        what="EP-09 counting the 2 succeeded jobs",
        source_id=twice_id,
        status="succeeded",
    )
    assert succeeded["total"] == 2, f"both crawls succeeded: {succeeded}"
    for status in ("failed", "active"):
        none_of_status = expect_json(api.list_jobs(source_id=twice_id, status=status), 200)
        assert (none_of_status["total"], none_of_status["items"]) == (0, []), (
            f"no job of {twice_id} is {status}: {none_of_status}"
        )

    # 範囲外のページ
    beyond_last_page = wait_for_job_list(
        api,
        lambda body: body["total"] == 2,
        what="EP-09 counting the 2 jobs on a page past the end",
        source_id=twice_id,
        page=2,
    )
    assert (beyond_last_page["items"], beyond_last_page["total"], beyond_last_page["page"]) == (
        [],
        2,
        2,
    ), f"a page past the end is empty but not an error: {beyond_last_page}"

    # 全ジョブの total は、loreley-jobs の直接の件数と一致する(すべてのテストのジョブを含む)
    def job_count(status: str | None) -> int:
        filters: list[dict[str, Any]] = [{"term": {"record_type": "job"}}]
        if status is not None:
            filters.append({"term": {"status": status}})
        return opensearch.count(JOBS_INDEX, {"bool": {"filter": filters}})

    for status in (None, "succeeded"):
        query: dict[str, str] = {} if status is None else {"status": status}
        listing = poll_until(
            lambda query=query: expect_json(api.list_jobs(**query), 200),
            lambda body, status=status: body["total"] == job_count(status),
            timeout_secs=READ_LAG_TIMEOUT_SECONDS,
            poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
            what=f"EP-09 total matching the direct count of the jobs (status={status})",
        )
        assert listing["total"] >= 3, f"at least the 3 crawls of this module exist: {listing}"
        assert len(listing["items"]) == min(listing["total"], listing["items_per_page"])

    # 空の結果(404 にしない)
    for source_id in (crawled_sources.never_crawled.source_id, unique_id("q-unregistered")):
        empty = expect_json(api.list_jobs(source_id=source_id), 200)
        assert (empty["items"], empty["total"]) == ([], 0), (
            f"{source_id} has no job: an empty result, not 404: {empty}"
        )

    # EP-10: 最新のジョブだけが latest_for_source=true(検索で読むため、反映を待つ)
    def read_both_jobs() -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            expect_json(api.get_job(first_job_id), 200),
            expect_json(api.get_job(second_job_id), 200),
        )

    first_job, second_job = poll_until(
        read_both_jobs,
        lambda jobs: (jobs[0]["latest_for_source"], jobs[1]["latest_for_source"]) == (False, True),
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what="EP-10 marking only the newest crawl as latest_for_source",
    )
    for job in (first_job, second_job):
        assert (job["rerunnable"], job["rerun_blocked_reason"]) == (False, "not_failed"), (
            f"a succeeded job is not rerunnable: {job}"
        )


def test_opensearch_cluster_matches_the_direct_cat_and_health_reads(
    api: AdminApi, opensearch: OpenSearchProbe
) -> None:
    """【何を確認するか】(AIT-32)
    EP-12 が返す `cluster`・`nodes`・`indices`・`shards`・`total_indices` が、OpenSearch の
    `_cluster/health`・`_cat/nodes`・`_cat/indices`・`_cat/shards` を直接読んで独立に作った値と一致する
    こと。

    【前提と手順】
    前提: 単一ノードの OpenSearch、4 つの索引(検索インデックスは実体 `loreley-documents-000001`)。
    手順: 4 つの索引を refresh した後、EP-12 を呼ぶ。同じ引数(`format=json`・`bytes=b`・
    `expand_wildcards=all`)で `_cat/*` を直接読み、admin-api 7.1 の規則(整数・小文字・`p`/`r` の言い換え・
    索引の並び)で期待値を作る。一致するまで(読み取りの間の変化の分だけ)待つ。

    【期待する結果とその根拠】
    - `cluster` は `cluster_name`・`status`・`number_of_nodes`・`active_shards`・`relocating_shards`・
      `initializing_shards`・`unassigned_shards` と同じ値。`nodes` はノード名の昇順。
    - `indices` は `status`(小文字)・`document_count`(整数)つきで、状態の悪い順 → 名前の昇順。
      4 つの索引を含む。`shards` は索引・シャード番号・primary を先・ノード名の順で、`role`・`state` を
      正規化した値。`truncated=false`、`total_indices` は `indices` の件数(B 7.1)。

    【単体テストでは確認できず実機で確認する点】
    実 OpenSearch の `cat.*`(`format=json`・`h=`・`bytes=b`)の応答の形(値が文字列)と、api の
    正規化が一致すること。
    """

    def snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
        for index in (SEARCH_INDEX, JOBS_INDEX, SOURCES_INDEX, DELETIONS_INDEX):
            opensearch.refresh(index)
        body = expect_json(api.opensearch_cluster(), 200)
        actual = {key: body[key] for key in ("cluster", "nodes", "indices", "shards")}
        actual |= {key: body[key] for key in ("truncated", "total_indices")}
        return actual, _expected_cluster_view(opensearch)

    actual, _ = poll_until(
        snapshot,
        lambda state: state[0] == state[1],
        timeout_secs=READ_LAG_TIMEOUT_SECONDS,
        poll_interval_secs=READ_LAG_POLL_INTERVAL_SECONDS,
        what="EP-12 matching the direct reads of _cluster/health and _cat/*",
    )

    index_names = {index["name"] for index in actual["indices"]}
    assert index_names >= EXPECTED_INDEX_NAMES, f"the 4 indices must be listed: {index_names}"
    assert actual["cluster"]["node_count"] == len(actual["nodes"]) == 1, f"single node: {actual}"
    assert (actual["truncated"], actual["total_indices"]) == (False, len(actual["indices"]))


# --- AIT-30: 行ごとの期待値の独立計算 ---


def _expected_source_row(opensearch: OpenSearchProbe, config: dict[str, Any]) -> dict[str, Any]:
    """`loreley-sources` の 1 件から、EP-01 の 1 行の期待値を、OpenSearch の直読みだけで作る。"""
    source_id: str = config["_id"]
    status: str = config["_source"]["status"]
    jobs = opensearch.job_records_of(source_id)
    assert all(job["_source"]["status"] in TERMINAL_JOB_STATUSES for job in jobs), (
        f"every job must be finished (conftest waits for idle): {jobs}"
    )
    crawls = [job for job in jobs if job["_source"]["job_type"] == "crawl"]
    completed_at_values = [
        parse_instant(job["_source"]["finished_at"])
        for job in crawls
        if job["_source"]["status"] in _COMPLETED_STATUSES
    ]
    # `delete_job` は `deleting` のソースだけが持つ(B 3.1)。
    delete_job = None
    if status == "deleting":
        delete_job = _expected_brief(
            _latest_job([job for job in jobs if job["_source"]["job_type"] == "source_delete"])
        )
    return {
        "source_id": source_id,
        "status": status,
        "last_crawl": _expected_brief(_latest_job(crawls)),
        "last_completed_at": max(completed_at_values, default=None),
        "delete_job": delete_job,
        "document_count": opensearch.count_source_documents(source_id),
        "unavailable": {},
    }


def _latest_job(jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """`queued_at` が最新のジョブ。同時刻は `job_id` の昇順で先頭(admin-api 2.1・5.1)。"""
    if not jobs:
        return None
    latest_queued_at = max(job["_source"]["queued_at"] for job in jobs)
    return min(
        (job for job in jobs if job["_source"]["queued_at"] == latest_queued_at), key=_job_id
    )


def _job_id(job: dict[str, Any]) -> str:
    return str(job["_id"])


def _expected_brief(job: dict[str, Any] | None) -> dict[str, Any] | None:
    """終端のジョブ記録から `JobBrief` の期待値。終端なので `stalled`・`cancellable` は false。"""
    if job is None:
        return None
    record = job["_source"]
    brief: dict[str, Any] = {"job_id": job["_id"]}
    for key in ("source_id", "job_type", "trigger", "status", "force_delete", "rewrite_mode"):
        brief[key] = record.get(key)
    for key in _JOB_BRIEF_DATE_KEYS:
        brief[key] = parse_instant(record[key]) if record.get(key) else None
    brief["failure_reason"] = record.get("failure_reason") if record["status"] == "failed" else None
    brief["stalled"] = False
    brief["cancellable"] = False
    return brief


def _listed_source_row(item: dict[str, Any]) -> dict[str, Any]:
    """EP-01 の 1 行を、`_expected_source_row` と比べられる形(日時は `datetime`)にする。"""
    return {
        "source_id": item["source_id"],
        "status": item["status"],
        "last_crawl": _listed_brief(item["last_crawl"]),
        "last_completed_at": _optional_instant(item["last_completed_at"]),
        "delete_job": _listed_brief(item["delete_job"]),
        "document_count": item["document_count"],
        "unavailable": item["unavailable"],
    }


def _listed_brief(brief: dict[str, Any] | None) -> dict[str, Any] | None:
    if brief is None:
        return None
    return {
        key: _optional_instant(value) if key in _JOB_BRIEF_DATE_KEYS else value
        for key, value in brief.items()
    }


def _optional_instant(value: str | None) -> datetime | None:
    return None if value is None else parse_instant(value)


# --- AIT-32: クラスタの期待値の独立計算 ---


def _expected_cluster_view(opensearch: OpenSearchProbe) -> dict[str, Any]:
    """`_cluster/health`・`_cat/*` の直読みから、EP-12 の期待値(`fetched_at` を除く)を作る。"""
    health = opensearch.cluster_health()
    nodes = opensearch.cat_rows("nodes", "name")
    index_rows = opensearch.cat_rows("indices", "index,health,docs.count", expand_wildcards="all")
    shard_rows = opensearch.cat_rows("shards", "index,shard,prirep,state,node")

    indices = [
        {
            "name": row["index"],
            "status": row["health"].lower() if row["health"] else None,
            "document_count": int(row["docs.count"]) if row["docs.count"] else None,
        }
        for row in index_rows
    ]
    # シャードがあるのにインデックス一覧にない索引は、`status`・`document_count` を null で補う(B 7.1)。
    listed_names = {index["name"] for index in indices}
    for name in dict.fromkeys(
        row["index"] for row in shard_rows if row["index"] not in listed_names
    ):
        indices.append({"name": name, "status": None, "document_count": None})
    indices.sort(
        key=lambda index: (_INDEX_STATUS_RANK.get(index["status"] or "", 3), index["name"])
    )

    shards = [
        {
            "index": row["index"],
            "shard": int(row["shard"]),
            "role": _SHARD_ROLE_BY_PRIREP[row["prirep"].lower()],
            "state": row["state"].lower(),
            "node": row["node"] or None,
        }
        for row in shard_rows
    ]
    shards.sort(
        key=lambda shard: (
            shard["index"],
            shard["shard"],
            0 if shard["role"] == "primary" else 1,
            shard["node"] or "",
        )
    )
    return {
        "cluster": {
            "name": health["cluster_name"],
            "status": health["status"].lower(),
            "node_count": health["number_of_nodes"],
            "active_shards": health["active_shards"],
            "relocating_shards": health["relocating_shards"],
            "initializing_shards": health["initializing_shards"],
            "unassigned_shards": health["unassigned_shards"],
        },
        "nodes": [{"name": name} for name in sorted(row["name"] for row in nodes)],
        "indices": indices,
        "shards": shards,
        "truncated": False,
        "total_indices": len(indices),
    }

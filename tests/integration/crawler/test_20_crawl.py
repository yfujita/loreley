"""CIT-20〜CIT-23: クロール(`POST /sources/{source_id}/crawl-jobs`)の主要フロー。

目的:
    実 OpenSearch・実 Indexer(別コンテナ、HTTP 直接通信)・実 FileSystem(Docker のバインドマウント)で、
    クロール 1 回が最後まで通ることを確かめる。
      - CIT-20: 列挙・取得・登録・終了通知・削除結果の確認。Indexer の件数照合が成立する
      - CIT-21: Crawler 側の原本サイズ超過。記録され、件数照合に載る
      - CIT-22: 実行中のロックが `loreley-jobs` に存在し、終了後に解放される
      - CIT-23: 原本サイズ超過だったファイルを削除して再クロールすると、その記録が整理される

参照する設計書の章:
    - crawler-architecture-v0.4.md 4.5(ジョブの実行)、5.1(ロック)、6.4・6.5(スキップ・原本サイズ超過)、
      7.4〜7.7(Indexer への要請、終了通知、削除結果のポーリング、登録結果)
    - crawler-api-v0.4.md 4.1(クロール起動)
    - connector-file-system-v0.3.md(列挙の対象: 既定の拡張子、隠しファイルは対象外)
    - indexer-architecture-v0.10.md 9.6(件数照合 `enumerated_count == N_seen + E_missing`)
    - apps/crawler/README.md 8 章(実 Indexer が必要な項目: バッチ応答の `document_id` の照合、件数照合の独立検証)

扱うシナリオ: CIT-20(列挙〜件数照合)、CIT-21(原本サイズ超過)、CIT-22(ロックの実体)、CIT-23(原本サイズ超過記録の整理)
"""

from datetime import timedelta
from typing import Any

from support import (
    CRAWLER_OWNER,
    JOBS_INDEX,
    LOCK_POLL_INTERVAL_SECONDS,
    LOCK_WAIT_TIMEOUT_SECONDS,
    OVERSIZE_RAW_BYTES,
    TERMINAL_JOB_STATUSES,
    CrawlerApi,
    OpenSearchProbe,
    SourceDirectory,
    assert_job_succeeded,
    parse_instant,
    poll_until,
    run_crawl,
    start_job_ok,
    utc_now,
    wait_for_job,
    wait_for_lock_released,
)

# samples/ のうち、取り込まれる 5 件と、取り込まれない 2 件(samples/README.md)。
INDEXED_SAMPLES = (
    "sample.txt",
    "sample.md",
    "sample.html",
    "sample.pdf",
    "nested/sample-nested.txt",
)
IGNORED_SAMPLES = ("ignored.csv", ".hidden.txt")
# 取り込まれるファイルごとの検索用の語(samples/README.md)。
MARKERS = {
    "sample.txt": "txtmarkeralpha",
    "sample.md": "mdmarkerbeta",
    "sample.html": "htmlmarkergamma",
    "sample.pdf": "pdfmarkerdelta",
    "nested/sample-nested.txt": "nestedmarkerepsilon",
}
# 取り込まれないファイルの語。命中したら、対象外のファイルが索引された。
IGNORED_MARKERS = ("csvignoredmarker", "hiddenignoredmarker")


def test_crawl_indexes_the_documents_and_the_counts_reconcile(
    crawler_api: CrawlerApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】
    txt・md・html・pdf とサブディレクトリのファイル(5 件)と、対象外のファイル(`.csv`・隠しファイル)を
    置いたディレクトリのクロールが、`succeeded` で終わること。5 件だけが検索インデックスに入り、Crawler が
    計算した `document_id` が独立実装と一致し、Indexer の件数照合が成立すること。

    【前提と手順】
    前提: 登録済みのソース。ディレクトリに `samples/` の 7 ファイルを置く(外部 ID は相対パス)。
    手順: クロールを起動(202)→ ジョブの完了を待つ → ジョブ記録・検索インデックス・
    `loreley-deletions` の削除結果を、OpenSearch から直接読んで確認する。

    【期待する結果とその根拠】
    - ジョブは `succeeded`、`confirmation=confirmed`(削除結果が終端状態になったことを確認できた。
      architecture 7.6)。`registration` は `enumerated_count=5`・`created_count=5`・それ以外の件数が 0・
      `partial=false`(確定済み。7.7)。警告(`warnings`)は出ない。
    - 検索インデックスの文書の `document_id`(= `_id`)の集合が、テスト側の独立実装
      (SHA-256(`source_id` + NUL + 相対パス))で計算した 5 件と一致する。Crawler と Indexer が同じ値を
      使っている証拠(ずれると、Crawler は `document_id_mismatch` でジョブを失敗させる。CM-U-3)。
    - 検索用の語で、対応する文書が 1 件だけ命中する。対象外の 2 ファイルの語は命中しない(列挙の対象外。
      CFS-K-3、`include_hidden` の既定は `false`)。
    - `loreley-deletions` の `deletion_result-{job_id}` は `deleted`。`enumerated_count == n_seen + e_missing`
      (5 == 5 + 0。件数照合。Indexer arch 9.6)で、`validation_failed` ではない。TTL(600 秒)の期限内なので
      削除対象は 0(`target_count=0`、`deleted_count=0`)。
    - ジョブ終了時の記録の整理(スキップ・原本サイズ超過記録の全件走査と削除)は、`succeeded` で終わって
      いることから、実 OpenSearch で例外なく完了している(整理の失敗は、ジョブを `failed` にする)。

    【fake では確認できず実機で確認する点】
    Docker のバインドマウント(`:ro`)越しの列挙・取得、実 Indexer のバッチ応答の `document_id` の照合、
    実 OpenSearch での記録の整理(PIT と `search_after`)、Indexer との件数照合(README 8 章)。
    """
    # ディレクトリに、取り込まれる 5 件と対象外の 2 件を置く
    for relative_path in (*INDEXED_SAMPLES, *IGNORED_SAMPLES):
        registered_source.copy_sample(relative_path)
    source_id = registered_source.source_id

    # クロールを起動して、完了(succeeded)を待つ
    job = run_crawl(crawler_api, opensearch, source_id)

    assert job["job_type"] == "crawl", f"job_type must be crawl: {job}"
    assert job["trigger"] == "manual", f"trigger must be manual: {job}"
    assert job["owner"] == CRAWLER_OWNER, f"owner must be {CRAWLER_OWNER}: {job}"
    assert job["confirmation"] == "confirmed", f"the deletion result must be confirmed: {job}"
    expected_registration = {
        "enumerated_count": 5,
        "created_count": 5,
        "updated_count": 0,
        "unchanged_count": 0,
        "skipped_count": 0,
        "oversize_count": 0,
        "error_count": 0,
        "invalid_id_count": 0,
        "partial": False,
    }
    assert job["registration"] == expected_registration, (
        f"the 5 sample documents must all be created: {job['registration']}"
    )
    assert not job.get("warnings"), f"no warning is expected: {job.get('warnings')}"

    # 検索インデックス: 5 件で、document_id がテスト側の独立実装と一致する
    expected_ids = {registered_source.external_id_to_document_id(name) for name in INDEXED_SAMPLES}
    assert opensearch.source_document_ids(source_id) == expected_ids, (
        "the indexed document ids must equal the independently computed SHA-256 ids"
    )
    for relative_path, marker in MARKERS.items():
        hits = opensearch.search_content(source_id, marker)
        assert [hit["_id"] for hit in hits] == [
            registered_source.external_id_to_document_id(relative_path)
        ], f"{marker} must hit only {relative_path}: {[hit['_id'] for hit in hits]}"
    for marker in IGNORED_MARKERS:
        assert opensearch.search_content(source_id, marker) == [], (
            f"{marker} must not be indexed (the file is out of the enumeration target)"
        )

    # Indexer の削除結果: 件数照合が成立している
    result = opensearch.fetch_deletion_result(job["job_id"])
    assert result is not None, "the deletion result must exist in loreley-deletions"
    assert result["status"] == "deleted", (
        f"the deletion result must be deleted (not validation_failed): {result}"
    )
    assert result["enumerated_count"] == result["n_seen"] + result["e_missing"], (
        f"enumerated_count must equal n_seen + e_missing: {result}"
    )
    assert (result["enumerated_count"], result["n_seen"], result["e_missing"]) == (5, 5, 0), (
        f"5 enumerated, 5 seen, 0 missing: {result}"
    )
    assert (result["target_count"], result["deleted_count"]) == (0, 0), (
        f"nothing is expired: {result}"
    )


def test_crawl_records_an_oversize_document_and_the_counts_still_reconcile(
    crawler_api: CrawlerApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】
    Crawler の `MAX_RAW_BYTES`(65,536)を超える原本(70,000 バイト)が、スキップではなく原本サイズ超過として
    記録され、索引されず、終了通知の `oversize_document_ids` に載り、Indexer の件数照合が成立すること。

    【前提と手順】
    前提: 登録済みのソース。ディレクトリに通常のファイル(`sample.txt`)と、70,000 バイトのファイル
    (`big.txt`)を置く。
    手順: クロールを起動 → 完了を待つ → ジョブ記録・原本サイズ超過記録・検索インデックス・削除結果を読む。

    【期待する結果とその根拠】
    - ジョブは `succeeded`(原本サイズ超過だけでは `partially_succeeded` にしない。architecture 6.5)。
      `registration` は `enumerated_count=2`・`created_count=1`・`oversize_count=1`・`skipped_count=0`。
    - `loreley-jobs` の `oversize-{source_id}-{document_id}` が存在し、`detected_by=crawler`、
      `external_id=big.txt`、`last_job_id` がこのジョブ(6.5)。
    - 終了通知の内容(ジョブ記録の `finish_notice.content`)の `oversize_document_ids` が、`big.txt` の
      `document_id` だけ。`enumerated_count=2`。
    - `big.txt` は索引に入らず(検索インデックスは 1 件)、`sample.txt` は入る。
    - 件数照合: `enumerated_count == n_seen + e_missing`(2 == 1 + 1)。Indexer は、`oversize_document_ids` の
      文書を、索引になくても `E_missing` に数える(Indexer arch 9.6)ので、`validation_failed` にならず
      `deleted` になる。

    【fake では確認できず実機で確認する点】
    実際のファイルサイズによる原本サイズ超過の判定(FileSystem Connector の取得)と、実 Indexer が
    `oversize_document_ids` を `E_missing` として件数照合に使うこと。
    """
    registered_source.copy_sample("sample.txt")
    registered_source.write("big.txt", b"x" * OVERSIZE_RAW_BYTES)
    source_id = registered_source.source_id
    big_document_id = registered_source.external_id_to_document_id("big.txt")

    # クロールを起動して、完了(succeeded)を待つ
    job = run_crawl(crawler_api, opensearch, source_id)

    registration = job["registration"]
    assert (
        registration["enumerated_count"],
        registration["created_count"],
        registration["oversize_count"],
        registration["skipped_count"],
    ) == (2, 1, 1, 0), f"2 enumerated, 1 created, 1 oversize, 0 skipped: {registration}"
    record = opensearch.fetch_source(JOBS_INDEX, f"oversize-{source_id}-{big_document_id}")
    assert record is not None, (
        "the oversize record must exist in loreley-jobs "
        "(this test assumes MAX_RAW_BYTES=65536 in compose.test.yaml)"
    )
    assert record["detected_by"] == "crawler", f"the Crawler must detect the oversize: {record}"
    assert record["external_id"] == "big.txt", f"external_id must be the relative path: {record}"
    assert record["last_job_id"] == job["job_id"], f"last_job_id must be this job: {record}"
    notice = job["finish_notice"]["content"]
    assert notice["oversize_document_ids"] == [big_document_id], (
        f"the finish notice must carry the oversize document id: {notice}"
    )
    assert notice["enumerated_count"] == 2, f"the finish notice must count both files: {notice}"

    # 索引: sample.txt だけが入る
    assert opensearch.source_document_ids(source_id) == {
        registered_source.external_id_to_document_id("sample.txt")
    }, "only the normal file may be indexed"

    # Indexer の件数照合: oversize が E_missing に数えられ、validation_failed にならない
    result = opensearch.fetch_deletion_result(job["job_id"])
    assert result is not None, "the deletion result must exist in loreley-deletions"
    assert result["status"] == "deleted", f"the reconciliation must pass: {result}"
    assert (result["enumerated_count"], result["n_seen"], result["e_missing"]) == (2, 1, 1), (
        f"2 enumerated = 1 seen + 1 missing: {result}"
    )


def test_oversize_record_is_purged_when_the_file_is_removed(
    crawler_api: CrawlerApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】(CIT-23)
    原本サイズ超過だったファイルがなくなってから再クロールすると、その原本サイズ超過記録が整理(削除)
    されること(CIT-20 では記録がなく空振りになる、実 OpenSearch での記録の整理を、記録がある状態で確認する)。

    【前提と手順】
    前提: 登録済みのソース。1 回目のクロールで `big.txt`(70,000 バイト)の原本サイズ超過記録ができている。
    手順: `big.txt` を消して、再度クロールする → 記録の有無を読む。

    【期待する結果とその根拠】
    1 回目: 記録が存在する(前提の確認)。2 回目: ジョブは `succeeded` で、記録は存在しない。
    クロール終了後の整理は、「今回もその種類の結果になった文書」の記録だけを残し、列挙されなかった
    文書の記録は消す(architecture 6.4 の (b)「列挙されなかった」)。

    【fake では確認できず実機で確認する点】
    記録の整理が使う全件走査(PIT と `search_after`)と、バルク削除が、実 OpenSearch で動くこと。
    """
    registered_source.copy_sample("sample.txt")
    registered_source.write("big.txt", b"x" * OVERSIZE_RAW_BYTES)
    source_id = registered_source.source_id
    run_crawl(crawler_api, opensearch, source_id)
    assert len(opensearch.oversize_records(source_id)) == 1, "the oversize record must exist first"

    # big.txt を消して、再度クロールする
    registered_source.remove("big.txt")
    run_crawl(crawler_api, opensearch, source_id)

    assert opensearch.oversize_records(source_id) == [], (
        "the oversize record of the removed file must be purged"
    )


def test_lock_exists_while_the_crawl_runs_and_is_released_afterwards(
    crawler_api: CrawlerApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】
    クロールの実行中、ソースのロック文書 `lock-{source_id}` が `loreley-jobs` に実在し、所有者・ジョブ ID・
    リース期限が正しいこと。ジョブの終了後にロック文書が消えること。

    【前提と手順】
    前提: 登録済みのソースに 5 件を置く。ポーリング間隔は、Crawler の削除結果のポーリング(2 秒)の間に
    ロックが存在する窓ができるよう、compose.test.yaml で短くしてある。
    手順: クロールを起動 → ロックにリース期限が付く(実行が始まる)まで 0.2 秒間隔で観測する → ロック文書の
    内容を確認 → ジョブの完了を待つ → ロック文書が消えるのを待つ。

    【期待する結果とその根拠】
    - 実行中のロック: `owner=crawler-1`(compose の `LORELEY_CRAWLER_OWNER`)、`job_id` がこのジョブ、
      `lease_expires_at` が未来(リース 300 秒。architecture 5.1)。受付はロックを `lease_expires_at=null` で
      作り(`queued`)、実行の開始でリースを設定するので、リースが付いたロックの観測は、実行中の証拠になる。
    - 終了後: ロック文書は存在しない(ロックの解放は、最終状態の記録の後に Job Runner が行う。4.5)。
      ジョブ記録が終端になった直後はまだ残りうるので、有限のポーリングで待つ。
    - 観測の窓が足りなかった(ジョブが終わるまでロックを観測できなかった)場合は、失敗として報告する。
      Indexer がロックを所有確認に使うので、ロックの実体が実 OpenSearch に存在することは、実機でしか
      確認できない。

    【fake では確認できず実機で確認する点】
    実 OpenSearch の `loreley-jobs` に、Indexer が読む形式(`owner`・`job_id`・`lease_expires_at`)の
    ロック文書が実際に作られ、リースが更新され、終了後に削除されること。
    """
    for relative_path in INDEXED_SAMPLES:
        registered_source.copy_sample(relative_path)
    source_id = registered_source.source_id

    # クロールを起動する
    job_id = start_job_ok(crawler_api.start_crawl(source_id), job_type="crawl", source_id=source_id)

    # ロックにリース期限が付く(実行が始まる)か、ジョブが終わるまで観測する
    def observe() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        return opensearch.fetch_lock(source_id), opensearch.fetch_job(job_id)

    def is_running_lock_or_finished(
        state: tuple[dict[str, Any] | None, dict[str, Any] | None],
    ) -> bool:
        lock, job = state
        has_lease = lock is not None and lock.get("lease_expires_at") is not None
        is_finished = job is not None and job.get("status") in TERMINAL_JOB_STATUSES
        return has_lease or is_finished

    lock, job = poll_until(
        observe,
        is_running_lock_or_finished,
        timeout_secs=LOCK_WAIT_TIMEOUT_SECONDS,
        poll_interval_secs=LOCK_POLL_INTERVAL_SECONDS,
        what=f"the lock of {source_id} having a lease while job {job_id} runs",
    )

    assert lock is not None and lock.get("lease_expires_at") is not None, (
        f"the lock was not observed while the job ran (the window was too short): "
        f"lock={lock}, job status={job['status'] if job else None}"
    )
    assert lock["record_type"] == "lock", f"record_type must be lock: {lock}"
    assert lock["owner"] == CRAWLER_OWNER, f"owner must be {CRAWLER_OWNER}: {lock}"
    assert lock["job_id"] == job_id, f"job_id must be the running job: {lock}"
    lease_expires_at = parse_instant(lock["lease_expires_at"])
    assert lease_expires_at > utc_now(), f"the lease must not have expired: {lock}"
    # リースは 300 秒。1 時間は、ホストと VM の時計差を許したうえで、遠い未来の時刻を弾く幅。
    assert lease_expires_at < utc_now() + timedelta(hours=1), (
        f"the lease must be a short one (300 seconds), not a distant time: {lock}"
    )

    # ジョブの完了を待つ
    finished_job = wait_for_job(opensearch, job_id)
    assert_job_succeeded(finished_job)

    # 終了後: ロックが解放される
    wait_for_lock_released(opensearch, source_id)

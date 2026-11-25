"""AIT-40・AIT-41: 文書の確認(EP-11 と、EP-10・01 への反映)。

目的:
    確認が必要な文書(抽出失敗・原本サイズ超過・スキップ・要約未生成)を返す EP-11 が、実 Crawler・
    実 Indexer が書いた実データを、実 OpenSearch のクエリ(`term` の絞り込み・`sort` の同順位・
    `from`/`size`・`ids`)でタブごとに正しく数え・ページ分けし・並べることを確かめる。
      - AIT-40: 1 回のクロールで、通常の md・壊れた PDF・上限を超える原本ができ、`tab_counts`・
        `document_count`・ページング・並び順・EP-10 の件数が、直読みの独立計算と一致すること
      - AIT-41: スキップ記録の `existence`(`existing`・`new`)が、検索インデックスへの `ids` クエリで
        決まること
    単体テストでは OpenSearch は fake で、実際に書かれた記録の形・同順位の並び・`ids` クエリの結果を
    確認できない。入力検証(`tab`・`page` の違反)と `unavailable` の全分岐は単体テストで済んでおり、
    ここでは再検証しない。

参照する設計書の章:
    - admin-api-v0.1.md 2.1(ページング・同順位)、3.1(EP-01 の文書数)、5.2(EP-10 の登録件数)、
      6.1(EP-11)
    - crawler-architecture-v0.4.md 3.3.3・3.3.4(スキップ記録・原本サイズ超過記録)、6.5(原本サイズ超過)、
      7.7(登録結果の集計)
    - indexer-architecture-v0.10.md(抽出失敗は `index_status=extract_failed` として登録する)

扱うシナリオ: AIT-40(件数・ページング・並び順)、AIT-41(`existence`)

AIT-41 は、実 Crawler にスキップを起こさせられない(取得の権限エラーを macOS の bind mount で確実に
作れない)ので、スキップ記録だけを OpenSearch に直接書く(前提作りだけ。判定は Admin API の応答で行う)。
Crawler が書いた記録との形式の照合(AAPI-U-7)は、未検証のまま。

検索で読む EP(EP-11 の `extract_failed`・文書数、EP-01)は、書き込みの反映が最大約 1 秒遅れる
(AAA-P-6)ので、期待する状態になるまで上限つきで待ってから確認する。
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from support import (
    SEARCH_INDEX,
    AdminApi,
    OpenSearchProbe,
    SourceDirectory,
    expect_json,
    format_instant,
    parse_instant,
    run_crawl,
    wait_for_document_list,
    wait_for_source_row,
)

NORMAL_FILE_COUNT = 3
BROKEN_PDF_COUNT = 26
OVERSIZE_FILE_COUNT = 2
# compose.test.yaml の `MAX_RAW_BYTES`(65,536 バイト)を超える大きさ。
OVERSIZE_FILE_BYTES = 70_000
DEFAULT_ITEMS_PER_PAGE = 25


def test_review_tabs_count_page_and_order_the_extract_failed_and_oversize_documents(
    api: AdminApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】(AIT-40)
    通常の md 3 件・壊れた PDF 26 件・上限超過の原本 2 件を 1 回クロールしたあと、EP-11 の `tab_counts`・
    `document_count`、`extract_failed` タブのページング(25 + 1)・並び(既定・昇順・同順位)・
    `items_per_page=50`、`oversize` タブの項目、EP-10 の `oversize_count`・`error_count` が、
    OpenSearch の直読みと独立に計算した期待値に一致すること。

    【前提と手順】
    前提: 登録済みのソースに、md 3 件、`.pdf` だが PDF でない壊れたファイル 26 件(内容は 1 件ずつ
    異なる)、70,000 バイトのファイル 2 件(Crawler・Indexer の上限は 65,536 バイト)。
    手順: クロールを 1 回行い(`succeeded`)、EP-11 を各タブ・ページ・`sort`・`items_per_page` で呼ぶ。
    期待する `document_id` は独立実装(`compute_document_id`)で、並びと項目の値は検索インデックス・
    `loreley-jobs` の直読みで作る。EP-01・EP-10 も読む。

    【期待する結果とその根拠】
    - EP-11 の `tab_counts` は `skipped=0`・`extract_failed=26`・`oversize=2`・`summary_pending=0`、
      `document_count=29`(md 3 + 抽出失敗 26。抽出失敗の文書も登録済みで、上限超過の原本は索引に
      ない。B 3.1・6.1)。EP-01 の同じソースの `document_count` も 29。最上位 `unavailable` は `{}`。
    - `extract_failed` の 1 ページ目は 25 件、2 ページ目は 1 件で、`total=26`。2 ページの和集合は
      独立計算の 26 件と一致し、重複しない。
    - 既定の並び(`-last_seen_at`)は、直読みの `last_seen_at` の降順で、同じ時刻は `document_id` の
      昇順(B 2.1。1 回のクロールの文書は `last_seen_at` が同じなので、同順位の規則が効く)。
      `sort=last_seen_at` は昇順でも同順位は `document_id` の昇順。`items_per_page=50` は 26 件を
      同じ順で 1 ページに返す。各行の `external_id`・`mime_type`(`application/pdf`)・`size`・`title`・
      日時は、検索インデックスの値と同じ。
    - `oversize` タブは 2 件で、既定の並び(`-last_detected_at`、同順位は `document_id` の昇順)。
      各行の `external_id`・`detected_by`・`size`・日時・`last_job_id` は、`loreley-jobs` の原本サイズ
      超過記録と同じで、`last_job_id` はこのクロール。`skipped`・`summary_pending` は 0 件。
    - EP-10: `registration` の `enumerated_count=31`・`created_count=29`・`oversize_count=2`・
      `error_count=26`・`skipped_count=0`(抽出失敗と原本サイズ超過はジョブの状態に影響しない。
      crawler-architecture 4.2・7.7)。

    【単体テストでは確認できず実機で確認する点】
    実 Indexer が抽出に失敗した文書を `extract_failed` で登録し、実 Crawler が上限超過を記録すること、
    それを実 OpenSearch の `term` の絞り込み・`sort`(同順位は `document_id`)・`from`/`size` が正しく
    数え・ページ分けすること。
    """
    source_id = registered_source.source_id
    normal_paths = [f"note-{number}.md" for number in range(1, NORMAL_FILE_COUNT + 1)]
    broken_paths = [f"broken/b{number:02d}.pdf" for number in range(1, BROKEN_PDF_COUNT + 1)]
    oversize_paths = [f"big-{number}.txt" for number in range(1, OVERSIZE_FILE_COUNT + 1)]
    for path in normal_paths:
        registered_source.write(path, f"# {path}\n\ntext of {path}\n".encode())
    for path in broken_paths:
        # PDF のヘッダがないので、抽出に失敗する。ファイルごとに内容を変える。
        registered_source.write(path, f"This is not a PDF file: {path}\n".encode())
    for path in oversize_paths:
        registered_source.write(path, b"x" * OVERSIZE_FILE_BYTES)

    job = run_crawl(api, opensearch, source_id)

    expected_ids = {
        "normal": {registered_source.document_id_of(path) for path in normal_paths},
        "broken": {registered_source.document_id_of(path) for path in broken_paths},
        "oversize": {registered_source.document_id_of(path) for path in oversize_paths},
    }
    document_count = NORMAL_FILE_COUNT + BROKEN_PDF_COUNT

    # OpenSearch の直読み: 索引にあるのは md と壊れた PDF だけ。上限超過は記録だけが残る。
    indexed = {hit["_id"]: hit["_source"] for hit in opensearch.source_documents(source_id)}
    assert set(indexed) == expected_ids["normal"] | expected_ids["broken"], (
        f"only the normal and the broken files must be indexed: {sorted(indexed)}"
    )
    failed_hits = {
        document_id: record
        for document_id, record in indexed.items()
        if record["index_status"] == "extract_failed"
    }
    assert set(failed_hits) == expected_ids["broken"], "the broken PDFs must be extract_failed"
    oversize_records = {
        record["_source"]["document_id"]: record["_source"]
        for record in opensearch.oversize_records(source_id)
    }
    assert set(oversize_records) == expected_ids["oversize"], "the big files must have records"
    last_seen_values = {record["last_seen_at"] for record in failed_hits.values()}
    assert len(last_seen_values) == 1, (
        f"one crawl must give the documents the same last_seen_at (the tie-break is tested): "
        f"{sorted(last_seen_values)}"
    )

    # tab_counts・document_count(検索で読むので、反映を待つ)
    first_page = wait_for_document_list(
        api,
        source_id,
        lambda body: body["total"] == BROKEN_PDF_COUNT and body["document_count"] == document_count,
        what="EP-11 counting the extract_failed documents and the registered documents",
        tab="extract_failed",
    )
    assert first_page["tab_counts"] == {
        "skipped": 0,
        "extract_failed": BROKEN_PDF_COUNT,
        "oversize": OVERSIZE_FILE_COUNT,
        "summary_pending": 0,
    }, f"the counts of the 4 tabs must match the 4 kinds of documents: {first_page['tab_counts']}"
    assert first_page["unavailable"] == {}, f"nothing may be unavailable: {first_page}"
    row = wait_for_source_row(
        api,
        source_id,
        lambda row: row["document_count"] == document_count,
        what=f"EP-01 counting the {document_count} registered documents",
    )
    assert row["document_count"] == document_count == first_page["document_count"]

    # extract_failed のページング(25 + 1)
    assert len(first_page["items"]) == DEFAULT_ITEMS_PER_PAGE, (
        f"page 1 must have {DEFAULT_ITEMS_PER_PAGE} items: {len(first_page['items'])}"
    )
    second_page = expect_json(api.list_documents(source_id, tab="extract_failed", page=2), 200)
    assert (second_page["page"], second_page["total"], len(second_page["items"])) == (
        2,
        BROKEN_PDF_COUNT,
        BROKEN_PDF_COUNT - DEFAULT_ITEMS_PER_PAGE,
    ), f"page 2 must have the remaining item: {second_page}"
    paged_ids = [item["document_id"] for item in [*first_page["items"], *second_page["items"]]]
    assert len(paged_ids) == len(set(paged_ids)), f"no document may appear twice: {paged_ids}"
    assert set(paged_ids) == expected_ids["broken"], "the 2 pages must cover the 26 documents"

    # 並び: 既定は -last_seen_at(同時刻は document_id 昇順)。昇順でも同順位は document_id 昇順
    by_id_then_last_seen_desc = sorted(
        sorted(failed_hits),
        key=lambda document_id: failed_hits[document_id]["last_seen_at"],
        reverse=True,
    )
    by_id_then_last_seen_asc = sorted(
        sorted(failed_hits), key=lambda document_id: failed_hits[document_id]["last_seen_at"]
    )
    assert paged_ids == by_id_then_last_seen_desc, (
        f"the default order must be -last_seen_at: {paged_ids}"
    )
    ascending = expect_json(
        api.list_documents(source_id, tab="extract_failed", sort="last_seen_at", items_per_page=50),
        200,
    )
    assert [item["document_id"] for item in ascending["items"]] == by_id_then_last_seen_asc, (
        "sort=last_seen_at must keep document_id ascending for the same time"
    )
    all_in_one_page = expect_json(
        api.list_documents(source_id, tab="extract_failed", items_per_page=50), 200
    )
    assert [item["document_id"] for item in all_in_one_page["items"]] == paged_ids, (
        "items_per_page=50 must return the 26 documents in the same order"
    )

    # 行の項目は検索インデックスの値と同じ
    for item in all_in_one_page["items"]:
        stored = failed_hits[item["document_id"]]
        assert item["external_id"] in broken_paths, f"external_id: {item}"
        assert item["mime_type"] == "application/pdf" == stored["mime_type"], f"mime_type: {item}"
        assert item["size"] == stored["size"], f"size must be stored one: {item}"
        assert item["title"] == stored["title"], f"title must be the stored one: {item}"
        assert parse_instant(item["last_seen_at"]) == parse_instant(stored["last_seen_at"])
        assert parse_instant(item["source_updated_at"]) == parse_instant(
            stored["source_updated_at"]
        )
        assert item["unavailable"] == {}, f"the row must have no failure: {item}"

    # oversize タブ
    oversize = expect_json(api.list_documents(source_id, tab="oversize"), 200)
    assert oversize["total"] == OVERSIZE_FILE_COUNT, f"2 oversize documents: {oversize}"
    # 既定の並びは -last_detected_at(同時刻は document_id 昇順)
    expected_oversize_order = sorted(
        sorted(oversize_records),
        key=lambda document_id: oversize_records[document_id]["last_detected_at"],
        reverse=True,
    )
    assert [item["document_id"] for item in oversize["items"]] == expected_oversize_order, (
        f"the default order must be -last_detected_at: {oversize['items']}"
    )
    for item in oversize["items"]:
        stored = oversize_records[item["document_id"]]
        assert item["external_id"] in oversize_paths, f"external_id: {item}"
        assert (item["detected_by"], item["size"], item["last_job_id"]) == (
            stored["detected_by"],
            stored["size"],
            stored["last_job_id"],
        ), f"the row must be the stored record: {item} / {stored}"
        assert item["last_job_id"] == job["job_id"], f"detected by this crawl: {item}"
        assert parse_instant(item["first_detected_at"]) == parse_instant(
            stored["first_detected_at"]
        )
        assert parse_instant(item["last_detected_at"]) == parse_instant(stored["last_detected_at"])
        assert item["unavailable"] == {}, f"the row must have no failure: {item}"

    # 確認が要らないタブは空
    for tab in ("skipped", "summary_pending"):
        empty = expect_json(api.list_documents(source_id, tab=tab), 200)
        assert (empty["items"], empty["total"]) == ([], 0), f"no document in tab {tab}: {empty}"

    # EP-10 の登録件数(抽出失敗・上限超過はジョブの状態に影響しない)
    registration = job["registration"]
    assert {
        name: registration[name]
        for name in (
            "enumerated_count",
            "created_count",
            "oversize_count",
            "error_count",
            "skipped_count",
        )
    } == {
        "enumerated_count": document_count + OVERSIZE_FILE_COUNT,
        "created_count": document_count,
        "oversize_count": OVERSIZE_FILE_COUNT,
        "error_count": BROKEN_PDF_COUNT,
        "skipped_count": 0,
    }, f"EP-10 must count the documents of each kind: {registration}"


def test_skipped_tab_tells_existing_documents_from_new_ones_by_the_ids_query(
    api: AdminApi, opensearch: OpenSearchProbe, registered_source: SourceDirectory
) -> None:
    """【何を確認するか】(AIT-41)
    `skipped` タブの各行の `existence` が、そのページの `document_id` を検索インデックスへ 1 回の `ids`
    クエリで問い合わせた結果(索引にあれば `existing`、なければ `new`)になること。`tab_counts`・並び・
    項目の値も確かめる。

    【前提と手順】
    前提: 登録済みのソースに md 1 件をクロール済み(索引にある)。スキップ記録を 2 件、OpenSearch に
    直接書く(前提作りだけ)。1 件はその文書(`last_skipped_at` が新しい)、もう 1 件は索引にない
    文書(古い)。形式は crawler-architecture 3.3.3。
    手順: EP-11 を `tab=skipped` で、既定と `sort=last_skipped_at` で呼ぶ。

    【期待する結果とその根拠】
    - `total=2`・`tab_counts.skipped=2`(他のタブは 0)・`document_count=1`。
    - 索引にある文書の行は `existence=existing`、索引にない文書の行は `new`(B 6.1)。
    - 既定の並び(`-last_skipped_at`)は 新しい記録 → 古い記録、`sort=last_skipped_at` は逆順(B 2.1)。
    - 各行の `external_id`・`stage`・`reason`(記録のまま)・`attempts`・`consecutive_skips`・日時・
      `last_job_id` は、書き込んだ値と同じで、行の `unavailable` は `{}`。

    【単体テストでは確認できず実機で確認する点】
    実 OpenSearch の `ids` クエリが、検索インデックス(エイリアス)の `_id` に対して、存在する ID だけを
    返すこと(AAA-U-2)。`document_id` の算出がテストの独立実装・Crawler・Indexer で一致すること
    (索引の `_id` と照合する)。
    ※ Crawler が実際に書いたスキップ記録との形式の照合(AAPI-U-7)は未検証(直接書き込みのため)。
    """
    source_id = registered_source.source_id
    registered_source.write("doc.md", b"# doc\n\ntext of doc\n")
    job = run_crawl(api, opensearch, source_id)

    existing_id = registered_source.document_id_of("doc.md")
    new_id = registered_source.document_id_of("never-indexed.md")
    indexed_ids = {hit["_id"] for hit in opensearch.source_documents(source_id)}
    assert indexed_ids == {existing_id}, (
        f"only doc.md is indexed, and its _id must be the independent document_id: {indexed_ids}"
    )

    # 秒未満を切り捨てた時刻で書く(OpenSearch には、ミリ秒の文字列で入る)
    now = datetime.now(UTC).replace(microsecond=0)
    records: dict[str, dict[str, Any]] = {
        existing_id: {
            "external_id": "doc.md",
            "stage": "fetch",
            "reason": "fetch_transient: 取得の一時的な失敗が続いた",
            "attempts": 3,
            "consecutive_skips": 2,
            "first_skipped_at": now - timedelta(days=3),
            "last_skipped_at": now - timedelta(hours=1),
        },
        new_id: {
            "external_id": "never-indexed.md",
            "stage": "fetch",
            "reason": "fetch_permission_denied: 取得の権限がなかった",
            "attempts": 1,
            "consecutive_skips": 1,
            "first_skipped_at": now - timedelta(days=1),
            "last_skipped_at": now - timedelta(days=1),
        },
    }
    for document_id, fields in records.items():
        opensearch.write_skip_record(
            source_id=source_id,
            document_id=document_id,
            last_job_id=job["job_id"],
            **fields,
        )

    newest_first = wait_for_document_list(
        api,
        source_id,
        lambda body: body["total"] == len(records) and body["document_count"] == 1,
        what="EP-11 listing the 2 skip records and the 1 registered document",
        tab="skipped",
    )
    assert newest_first["tab_counts"] == {
        "skipped": 2,
        "extract_failed": 0,
        "oversize": 0,
        "summary_pending": 0,
    }, f"only the skipped tab has documents: {newest_first['tab_counts']}"
    assert newest_first["unavailable"] == {}, f"nothing may be unavailable: {newest_first}"

    assert [item["document_id"] for item in newest_first["items"]] == [existing_id, new_id], (
        f"the default order must be -last_skipped_at: {newest_first['items']}"
    )
    oldest_first = expect_json(
        api.list_documents(source_id, tab="skipped", sort="last_skipped_at"), 200
    )
    assert [item["document_id"] for item in oldest_first["items"]] == [new_id, existing_id], (
        f"sort=last_skipped_at must reverse the order: {oldest_first['items']}"
    )

    existence_by_id = {item["document_id"]: item["existence"] for item in newest_first["items"]}
    assert existence_by_id == {existing_id: "existing", new_id: "new"}, (
        f"existence must follow the ids query on the search index: {existence_by_id}"
    )
    for item in newest_first["items"]:
        written = records[item["document_id"]]
        assert {
            "external_id": item["external_id"],
            "stage": item["stage"],
            "reason": item["reason"],
            "attempts": item["attempts"],
            "consecutive_skips": item["consecutive_skips"],
            "last_job_id": item["last_job_id"],
        } == {
            "external_id": written["external_id"],
            "stage": written["stage"],
            "reason": written["reason"],
            "attempts": written["attempts"],
            "consecutive_skips": written["consecutive_skips"],
            "last_job_id": job["job_id"],
        }, f"the row must show the stored skip record: {item}"
        assert item["first_skipped_at"] == format_instant(written["first_skipped_at"])
        assert item["last_skipped_at"] == format_instant(written["last_skipped_at"])
        assert item["unavailable"] == {}, f"the row must have no failure: {item}"

    # 索引の _id を直接確認する(ghost は索引にない)
    assert opensearch.count(SEARCH_INDEX, {"ids": {"values": [existing_id, new_id]}}) == 1, (
        "exactly the existing document must be in the search index"
    )

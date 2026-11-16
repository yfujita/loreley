"""チャンク処理(architecture 4.6・7.3・7.7。テスト観点 #1・#2・#7・#8・#9・#20)。

`last-seen` -> 取得 -> バッチ登録の順、取得と登録の交互の進行、バッチの閉じ条件、
`enumerated_count` の数え方、登録結果の集計と `partial` の遷移、件数照合のための ID 集合。
"""

from collections.abc import Sequence
from typing import Any

import pytest

from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
)
from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.crawl.executor import ReadyToFinish
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import (
    BatchResults,
    Change,
    DocumentRegistered,
    FailureType,
    IndexerRejected,
)
from tests.crawl.support import CrawlEnv, crawl_env, document_id_of
from tests.fakes.fake_connector import CONNECTOR_CLOSE, FETCH, STREAM_CLOSE, fetched_document
from tests.fakes.fake_indexer_client import REGISTER_DOCUMENTS, REPORT_LAST_SEEN

NAMES = ["a.txt", "b.txt", "c.txt", "d.txt", "e.txt"]


def files_of(names: Sequence[str], content: bytes = b"x") -> dict[str, bytes]:
    return {name: content for name in names}


def run_to_finish(env: CrawlEnv) -> ReadyToFinish:
    result = env.run()
    assert isinstance(result, ReadyToFinish)
    return result


def test_the_order_is_start_then_last_seen_before_fetch_then_register() -> None:  # 観点 #2
    with crawl_env(
        files=files_of(NAMES), settings=CrawlSettings(chunk_size=2, batch_max_documents=2)
    ) as env:
        run_to_finish(env)

        assert env.events == [
            "start",
            "last_seen:2",
            "fetch:a.txt",
            "fetch:b.txt",
            "register:a.txt,b.txt",
            "last_seen:2",
            "fetch:c.txt",
            "fetch:d.txt",
            "register:c.txt,d.txt",
            "last_seen:1",
            "fetch:e.txt",
            "register:e.txt",
        ]


def test_fetching_and_registration_alternate_inside_a_chunk() -> None:  # 観点 #9
    with crawl_env(
        files=files_of(NAMES), settings=CrawlSettings(chunk_size=5, batch_max_documents=2)
    ) as env:
        run_to_finish(env)

        assert env.events == [
            "start",
            "last_seen:5",
            "fetch:a.txt",
            "fetch:b.txt",
            "register:a.txt,b.txt",
            "fetch:c.txt",
            "fetch:d.txt",
            "register:c.txt,d.txt",
            "fetch:e.txt",
            "register:e.txt",
        ]


def test_a_batch_closes_before_the_raw_bytes_would_exceed_the_limit() -> None:
    with crawl_env(
        files=files_of(["a", "b", "c"], b"123456"),
        settings=CrawlSettings(batch_max_raw_bytes=10),
    ) as env:
        run_to_finish(env)

        batches = [call.arguments["documents"] for call in env.indexer.calls_of(REGISTER_DOCUMENTS)]
        assert [[d.external_id for d in batch] for batch in batches] == [["a"], ["b"], ["c"]]


def test_a_batch_holds_documents_up_to_the_byte_limit() -> None:
    with crawl_env(
        files=files_of(["a", "b", "c"], b"1234"),
        settings=CrawlSettings(batch_max_raw_bytes=10),
    ) as env:
        run_to_finish(env)

        batches = [call.arguments["documents"] for call in env.indexer.calls_of(REGISTER_DOCUMENTS)]
        assert [[d.external_id for d in batch] for batch in batches] == [["a", "b"], ["c"]]


def test_a_single_document_larger_than_the_batch_byte_limit_is_sent_alone() -> None:
    with crawl_env(
        files=files_of(["a"], b"0123456789ab"), settings=CrawlSettings(batch_max_raw_bytes=10)
    ) as env:
        run_to_finish(env)

        assert env.events[-1] == "register:a"


def test_last_seen_ids_are_split_by_the_request_limit_and_precede_any_fetch() -> None:
    with crawl_env(
        files=files_of(NAMES), settings=CrawlSettings(chunk_size=5, last_seen_max_ids=2)
    ) as env:
        run_to_finish(env)

        assert env.events[:4] == ["start", "last_seen:2", "last_seen:2", "last_seen:1"]
        assert env.events[4] == "fetch:a.txt"
        ids = [
            id_
            for call in env.indexer.calls_of(REPORT_LAST_SEEN)
            for id_ in call.arguments["document_ids"]
        ]
        assert ids == [document_id_of(name) for name in NAMES]


def test_the_uploaded_documents_carry_the_prepared_values() -> None:  # 観点 #1
    with crawl_env(files={"docs/a.txt": b"hello"}) as env:
        run_to_finish(env)

        (document,) = env.indexer.calls_of(REGISTER_DOCUMENTS)[0].arguments["documents"]
        assert document.external_id == "docs/a.txt"
        assert document.raw_content == b"hello"
        assert document.size == 5
        assert document.content_hash == (
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
        )
        assert document.title == "docs/a.txt"
        assert document.mime_type == "text/plain"


def test_an_empty_enumeration_sends_no_last_seen_and_no_batch() -> None:
    with crawl_env(files={}) as env:
        run_to_finish(env)

        assert env.events == ["start"]
        assert env.job_body()["registration"]["partial"] is False


# --- enumerated_count と、件数照合のための ID 集合 ---


def test_enumerated_count_counts_unique_valid_documents_including_skips() -> None:  # 観点 #7
    refs = [
        DocumentRef("a.txt", "a.txt"),
        DocumentRef("a.txt", "a.txt"),  # 重複(元の external_id が同じ)
        DocumentRef("", "empty"),  # 識別子エラー
        DocumentRef("b.txt", "b.txt"),  # 取得できない(スキップ)
        DocumentRef("c.txt", "c.txt"),  # 原本サイズ超過
        DocumentRef("d.txt", "d.txt"),
    ]
    documents = {
        "a.txt": fetched_document(b"a"),
        "c.txt": fetched_document(b"x" * 100),
        "d.txt": fetched_document(b"d"),
    }
    with crawl_env(
        items=[*refs, Completed()],
        documents=documents,
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        result = run_to_finish(env)

        assert result.run.enumeration is not None
        assert result.run.enumeration.enumerated_count == 4
        registration = env.job_body()["registration"]
        assert registration == {
            "enumerated_count": 4,
            "created_count": 2,
            "updated_count": 0,
            "unchanged_count": 0,
            "skipped_count": 1,
            "oversize_count": 1,
            "error_count": 0,
            "invalid_id_count": 1,
            "partial": False,
        }
        # 識別子エラーの文書は、last-seen にも載らない。
        sent_ids = [
            id_
            for call in env.indexer.calls_of(REPORT_LAST_SEEN)
            for id_ in call.arguments["document_ids"]
        ]
        assert sorted(sent_ids) == sorted(
            document_id_of(n) for n in ["a.txt", "b.txt", "c.txt", "d.txt"]
        )


def test_unregistered_documents_are_kept_for_the_finish_notice() -> None:  # 観点 #8
    refs = [DocumentRef(n, n) for n in ["ok", "gone", "big", "rejected"]]
    documents = {
        "ok": fetched_document(b"ok"),
        "big": fetched_document(b"x" * 100),
        "rejected": fetched_document(b"r"),
    }
    with crawl_env(
        items=[*refs, Completed()],
        documents=documents,
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        env.indexer.registration_failures["rejected"] = FailureType.DOCUMENT_REJECTED

        result = run_to_finish(env)

        tally = result.run.tally
        assert set(tally.skipped_document_ids) == {
            document_id_of("gone"),
            document_id_of("rejected"),
        }
        assert tally.oversize_document_ids == (document_id_of("big"),)
        # 列挙した文書は、登録されたか、スキップ・サイズ超過のどちらかに載っている。
        registration = env.job_body()["registration"]
        assert registration["enumerated_count"] == (
            registration["created_count"]
            + registration["updated_count"]
            + registration["unchanged_count"]
            + len(tally.skipped_document_ids)
            + len(tally.oversize_document_ids)
        )


def test_an_oversize_document_is_not_counted_as_skipped_and_has_its_own_record() -> (
    None
):  # 観点 #22
    with crawl_env(
        files={"big": b"x" * 100}, documents_settings=DocumentsSettings(max_raw_bytes=10)
    ) as env:
        result = run_to_finish(env)

        assert result.run.tally.skipped_document_ids == ()
        assert env.skip_record_ids() == []
        (record_id,) = env.oversize_record_ids()
        record = env.jobs.jobs_repository.body_of(record_id)
        assert record is not None
        assert record["detected_by"] == "crawler"
        assert record["last_job_id"] == env.job_body()["job_id"]
        assert env.indexer.calls_of(REGISTER_DOCUMENTS) == []  # Indexer に送らない


def test_the_size_hint_over_the_limit_skips_the_read() -> None:
    ref = DocumentRef("big", "big", size_hint=100)
    with crawl_env(
        items=[ref, Completed()],
        documents={"big": fetched_document(b"x")},
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        run_to_finish(env)

        assert env.connector.fetch_calls == []
        (record_id,) = env.oversize_record_ids()
        record = env.jobs.jobs_repository.body_of(record_id)
        assert record is not None
        assert record["size"] == 100


# --- 登録結果の集計(観点 #20) ---


def registered(name: str, change: Change, *, extract_failed: bool = False) -> DocumentRegistered:
    return DocumentRegistered(name, document_id_of(name), change, extract_failed)


def test_the_batch_changes_and_extract_failures_are_counted() -> None:
    with crawl_env(files=files_of(["a", "b", "c", "d"])) as env:
        env.indexer.behavior.inject(
            REGISTER_DOCUMENTS,
            BatchResults(
                (
                    registered("a", Change.CREATED),
                    registered("b", Change.UPDATED),
                    registered("c", Change.UNCHANGED),
                    registered("d", Change.UPDATED, extract_failed=True),
                )
            ),
        )

        run_to_finish(env)

        registration = env.job_body()["registration"]
        assert (
            registration["created_count"],
            registration["updated_count"],
            registration["unchanged_count"],
            registration["error_count"],
        ) == (1, 2, 1, 1)


def test_partial_is_true_while_counting_and_false_once_confirmed() -> None:
    with crawl_env(files=files_of(["a", "b"]), settings=CrawlSettings(chunk_size=1)) as env:
        during_second_chunk: list[dict[str, Any]] = []
        env.indexer.behavior.before(REPORT_LAST_SEEN, lambda: None)  # 1 つ目のチャンク
        env.indexer.behavior.before(
            REPORT_LAST_SEEN,  # 2 つ目のチャンク: 1 つ目の登録の集計がジョブ記録に反映済み
            lambda: during_second_chunk.append(env.job_body()["registration"]),
        )

        run_to_finish(env)

        (counted,) = during_second_chunk
        assert counted["partial"] is True
        assert counted["created_count"] == 1
        assert counted["enumerated_count"] == 1  # 反映済みの値(2 つ目の文書は未反映)
        assert env.job_body()["registration"]["partial"] is False
        assert env.job_body()["registration"]["created_count"] == 2


def test_a_failure_before_confirmation_keeps_the_counts_with_partial_true() -> None:  # CA-K-15
    with crawl_env(files=files_of(["a", "b"]), settings=CrawlSettings(chunk_size=1)) as env:
        env.indexer.behavior.before(REPORT_LAST_SEEN, lambda: None)
        env.indexer.behavior.before(
            REPORT_LAST_SEEN,
            lambda: env.indexer.behavior.inject(
                REPORT_LAST_SEEN, IndexerRejected(400, "invalid_request")
            ),
        )

        env.run()

        body = env.job_body()
        assert body["status"] == "failed"
        assert body["registration"]["partial"] is True
        assert body["registration"]["created_count"] == 1
        assert body["registration"]["enumerated_count"] == 2


def test_registration_is_zero_and_partial_for_a_failure_before_any_counting() -> None:
    with crawl_env(seed_source=False) as env:
        env.run()

        assert env.job_body()["registration"] == {
            "enumerated_count": 0,
            "created_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
            "skipped_count": 0,
            "oversize_count": 0,
            "error_count": 0,
            "invalid_id_count": 0,
            "partial": True,
        }


# --- 識別子エラーの例 ---


def test_invalid_ids_are_counted_and_examples_are_kept_up_to_the_limit() -> None:
    refs = [DocumentRef(f"/bad{i}", i) for i in range(5)]
    with crawl_env(
        items=[*refs, Completed()], settings=CrawlSettings(invalid_id_example_limit=2)
    ) as env:
        result = run_to_finish(env)

        assert result.run.tally.invalid_id_count == 5
        assert [e.display_external_id for e in result.run.invalid_id_examples] == ["/bad0", "/bad1"]
        assert env.job_body()["registration"]["invalid_id_count"] == 5
        assert env.indexer.events == ["start"]


# --- リソースの解放 ---


def test_the_enumeration_and_the_connector_are_closed_after_a_normal_run() -> None:
    with crawl_env(files=files_of(["a"])) as env:
        run_to_finish(env)

        assert [stream.closed for stream in env.connector.streams] == [True]
        assert env.connector.close_count == 1


def test_the_enumeration_and_the_connector_are_closed_after_a_failure() -> None:
    error = ConnectorError.of(ErrorCategory.ENUMERATION_INCOMPLETE, "途中で失敗")
    with crawl_env(items=[DocumentRef("a", "a"), error]) as env:
        env.run()

        assert [stream.closed for stream in env.connector.streams] == [True]
        assert env.connector.close_count == 1


def test_a_connector_that_fails_to_close_does_not_change_the_result() -> None:
    with crawl_env(files=files_of(["a"])) as env:
        env.connector.behavior.inject(CONNECTOR_CLOSE, RuntimeError("close failed"))
        env.connector.behavior.inject(STREAM_CLOSE, RuntimeError("close failed"))

        assert isinstance(env.run(), ReadyToFinish)


def test_fetch_is_not_called_for_documents_after_the_last_one() -> None:
    with crawl_env(files=files_of(["a", "b"])) as env:
        run_to_finish(env)

        assert [call.key for call in env.connector.behavior.calls_of(FETCH)] == ["a", "b"]


@pytest.mark.parametrize("chunk_size", [1, 2, 3, 100])
def test_every_document_is_registered_once_whatever_the_chunk_size(chunk_size: int) -> None:
    with crawl_env(files=files_of(NAMES), settings=CrawlSettings(chunk_size=chunk_size)) as env:
        run_to_finish(env)

        registered_names = [
            d.external_id
            for call in env.indexer.calls_of(REGISTER_DOCUMENTS)
            for d in call.arguments["documents"]
        ]
        assert registered_names == NAMES


def test_documents_that_fill_the_batch_bytes_exactly_stay_in_the_batch() -> None:
    with crawl_env(
        files=files_of(["a", "b", "c"], b"12345"), settings=CrawlSettings(batch_max_raw_bytes=10)
    ) as env:
        run_to_finish(env)

        batches = [call.arguments["documents"] for call in env.indexer.calls_of(REGISTER_DOCUMENTS)]
        assert [[d.external_id for d in batch] for batch in batches] == [["a", "b"], ["c"]]

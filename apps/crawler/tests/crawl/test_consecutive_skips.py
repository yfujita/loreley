"""連続スキップの打ち切り(architecture 6.3。CA-P-20。テスト観点 #10)。

取得段階と登録段階を別々に数える。取得段階は取得の成功、登録段階は `status: ok` でリセットする。
`oversize` と識別子エラーは、計数もリセットもしない。上限は 3 件にして確かめる。
"""

from collections.abc import Sequence

from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
    ErrorScope,
)
from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.crawl.executor import FailureRecorded, ReadyToFinish
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import FailureType
from tests.crawl.support import CrawlEnv, crawl_env
from tests.fakes.fake_connector import FETCH, fetched_document

LIMIT = 3
SETTINGS = CrawlSettings(consecutive_skip_limit=LIMIT)


def names(count: int, prefix: str = "f") -> list[str]:
    return [f"{prefix}{i:02d}" for i in range(count)]


def fail_fetch_of(
    env: CrawlEnv, targets: Sequence[str], category: ErrorCategory = ErrorCategory.FETCH_NOT_FOUND
) -> None:
    for name in targets:
        error = (
            ConnectorError.of(category, "failure", scope=ErrorScope.DOCUMENT)
            if category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
            else ConnectorError.of(category, "failure")
        )
        env.connector.behavior.inject(FETCH, error, key=name, times=None)


def assert_aborted(env: CrawlEnv, result: object, stage: str) -> None:
    assert isinstance(result, FailureRecorded)
    body = env.job_body()
    assert body["status"] == "failed"
    assert body["failure_reason"] == "skip_limit_exceeded"
    assert stage in body["failure_detail"]


def files_of(all_names: Sequence[str]) -> dict[str, bytes]:
    return {name: b"x" for name in all_names}


# --- 取得段階 ---


def test_scattered_fetch_failures_do_not_abort_the_crawl() -> None:
    # 20 件中 10 件の読めないファイルが散在する(間に取得に成功する文書が入る)。
    everything = names(20)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        fail_fetch_of(env, everything[::2])

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert len(result.run.tally.skipped_document_ids) == 10


def test_consecutive_fetch_failures_abort_the_crawl_at_the_limit() -> None:
    everything = names(10)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        fail_fetch_of(env, everything[:LIMIT])

        result = env.run()

        assert_aborted(env, result, "fetch")
        assert len(env.skip_record_ids()) == LIMIT  # 打ち切るまでのスキップは記録する
        assert len(env.connector.fetch_calls) == LIMIT  # 以降の文書は取得しない


def test_one_fewer_consecutive_fetch_failure_than_the_limit_does_not_abort() -> None:
    everything = names(10)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        fail_fetch_of(env, everything[: LIMIT - 1])

        assert isinstance(env.run(), ReadyToFinish)


def test_a_successful_fetch_resets_the_fetch_count() -> None:
    everything = names(8)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        # 失敗 2 件 -> 成功 -> 失敗 2 件 -> 成功: 連続は最大 2 件。
        fail_fetch_of(env, [everything[0], everything[1], everything[3], everything[4]])

        assert isinstance(env.run(), ReadyToFinish)


def test_consecutive_connector_internal_errors_on_fetch_count_as_the_fetch_stage() -> None:
    everything = names(10)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        fail_fetch_of(env, everything[:LIMIT], ErrorCategory.CONNECTOR_INTERNAL_ERROR)

        assert_aborted(env, env.run(), "fetch")
        assert "connector_internal_error" in env.job_body()["failure_detail"]


def test_mixed_fetch_failure_kinds_count_together() -> None:
    everything = names(10)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        fail_fetch_of(env, everything[0:1], ErrorCategory.FETCH_NOT_FOUND)
        fail_fetch_of(env, everything[1:2], ErrorCategory.FETCH_PERMISSION_DENIED)
        fail_fetch_of(env, everything[2:3], ErrorCategory.FETCH_TRANSIENT)

        assert_aborted(env, env.run(), "fetch")


# --- 登録段階 ---


def test_consecutive_rejected_documents_abort_the_crawl_at_the_limit() -> None:
    everything = names(6)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        for name in everything[:LIMIT]:
            env.indexer.registration_failures[name] = FailureType.DOCUMENT_REJECTED

        result = env.run()

        assert_aborted(env, result, "index")
        assert len(env.skip_record_ids()) == LIMIT


def test_scattered_rejected_documents_in_one_batch_do_not_abort_the_crawl() -> None:
    # 拒否される文書の間に、登録に成功する文書が入る。再送を終えて拒否が確定する順ではなく、
    # バッチの文書の順で数えるので、連続にならない。
    everything = names(8)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        for name in everything[::2]:
            env.indexer.registration_failures[name] = FailureType.DOCUMENT_REJECTED

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert len(result.run.tally.skipped_document_ids) == 4


def test_a_registered_document_resets_the_registration_count() -> None:
    everything = names(5)  # 拒否・拒否・成功・拒否・拒否
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        for name in [everything[0], everything[1], everything[3], everything[4]]:
            env.indexer.registration_failures[name] = FailureType.DOCUMENT_REJECTED

        assert isinstance(env.run(), ReadyToFinish)


def test_rejections_across_batches_are_counted_consecutively() -> None:
    everything = names(6)
    settings = CrawlSettings(consecutive_skip_limit=LIMIT, batch_max_documents=1)
    with crawl_env(files=files_of(everything), settings=settings) as env:
        for name in everything[:LIMIT]:
            env.indexer.registration_failures[name] = FailureType.DOCUMENT_REJECTED

        assert_aborted(env, env.run(), "index")


# --- 段階の独立 ---


def test_fetch_and_registration_failures_are_counted_separately() -> None:
    everything = names(8)
    with crawl_env(files=files_of(everything), settings=SETTINGS) as env:
        # 取得の失敗が 2 件、登録の拒否が 2 件。合わせれば 4 件だが、段階ごとには 3 件に届かない。
        fail_fetch_of(env, everything[:2])
        for name in everything[2:4]:
            env.indexer.registration_failures[name] = FailureType.DOCUMENT_REJECTED

        result = env.run()

        assert isinstance(result, ReadyToFinish)
        assert len(result.run.tally.skipped_document_ids) == 4


# --- oversize・識別子エラーは計数もリセットもしない ---


def test_oversize_documents_neither_count_nor_reset() -> None:
    refs = [DocumentRef(n, n) for n in ["f0", "big0", "f1", "big1", "f2", "f3"]]
    documents = {
        "big0": fetched_document(b"x" * 100),
        "big1": fetched_document(b"x" * 100),
        "f3": fetched_document(b"ok"),
    }
    with crawl_env(
        items=[*refs, Completed()],
        documents=documents,
        settings=SETTINGS,
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        # f0・f1・f2 は取得できない(連続 3 件)。間の oversize は、リセットしない。
        fail_fetch_of(env, ["f0", "f1", "f2"])

        assert_aborted(env, env.run(), "fetch")


def test_oversize_documents_do_not_add_to_the_count() -> None:
    refs = [DocumentRef(n, n) for n in ["f0", "big0", "f1", "big1", "f3"]]
    documents = {
        "big0": fetched_document(b"x" * 100),
        "big1": fetched_document(b"x" * 100),
        "f3": fetched_document(b"ok"),
    }
    with crawl_env(
        items=[*refs, Completed()],
        documents=documents,
        settings=SETTINGS,
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        fail_fetch_of(env, ["f0", "f1"])  # 失敗は 2 件。oversize を足しても 3 件にならない

        assert isinstance(env.run(), ReadyToFinish)


def test_invalid_ids_neither_count_nor_reset() -> None:
    refs = [
        DocumentRef("f0", "f0"),
        DocumentRef("/bad0", "bad0"),
        DocumentRef("f1", "f1"),
        DocumentRef("/bad1", "bad1"),
        DocumentRef("f2", "f2"),
    ]
    with crawl_env(items=[*refs, Completed()], settings=SETTINGS) as env:
        fail_fetch_of(env, ["f0", "f1", "f2"])

        assert_aborted(env, env.run(), "fetch")


def test_invalid_ids_do_not_add_to_the_count() -> None:
    refs = [
        DocumentRef("f0", "f0"),
        DocumentRef("/bad0", "bad0"),
        DocumentRef("/bad1", "bad1"),
        DocumentRef("f1", "f1"),
        DocumentRef("ok", "ok"),
    ]
    with crawl_env(
        items=[*refs, Completed()], documents={"ok": fetched_document(b"ok")}, settings=SETTINGS
    ) as env:
        fail_fetch_of(env, ["f0", "f1"])

        assert isinstance(env.run(), ReadyToFinish)

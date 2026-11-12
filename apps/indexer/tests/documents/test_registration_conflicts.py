"""登録の競合の再現(arch 16.1)。

実際の同時実行には頼らず、フックと応答の差し替えで決定的に再現する。
"""

import threading
from dataclasses import replace
from typing import Any

import pytest

from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.common.source_locks import SourceLocks
from loreley_indexer.documents import (
    Change,
    DocumentFailed,
    DocumentInput,
    DocumentOutcome,
    DocumentRegistered,
    DocumentRegistrar,
    FailureType,
    RegistrationConfig,
)
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    NotFound,
    OpenSearchUnavailableError,
)
from tests.crawl_runs.factories import CRAWL_STARTED_AT_TEXT
from tests.documents.conftest import MAX_REREADS
from tests.documents.factories import (
    id_of,
    make_context,
    make_document,
    register_one,
    stored_document,
)
from tests.fakes import in_memory_search_index as ops
from tests.fakes.concurrency import BLOCKED_PROBE_SECONDS, JOIN_TIMEOUT_SECONDS
from tests.fakes.in_memory_search_index import InMemorySearchIndex

pytestmark = pytest.mark.usefixtures("running_crawl")


def call_count(search_index: InMemorySearchIndex, *operations: str) -> int:
    return len(search_index.behavior.calls_of(*operations))


def write_other_changes(
    search_index: InMemorySearchIndex, document: DocumentInput, **changes: Any
) -> None:
    """別の書き手(要約の書き戻し、`last_seen_at` の Update など)が先に文書を更新する。"""
    current = stored_document(search_index, document)
    search_index.seed(id_of(document), {**current, **changes})


# --- C-18a: 409 → 読み直して再判定 ---


def test_write_that_loses_a_race_rereads_and_keeps_the_other_writers_change(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-6、C-18a、C-19a の裏側: 読んだあとに要約の書き戻しが先に入る。

    最初の PUT は 409 で書かれず、読み直した文書(新しい要約を含む)にメタデータ変更を載せて
    再度 PUT する。先に入った書き込みの内容は失われない。
    """
    document = make_document()
    register_one(registrar, document)
    search_index.behavior.before(
        ops.REPLACE,
        lambda: write_other_changes(
            search_index,
            document,
            summary="written by the summarizer",
            summary_status="generated",
            summary_model="m-1",
        ),
    )

    outcome = register_one(registrar, replace(document, title="B"))

    assert outcome.change is Change.UPDATED
    stored = stored_document(search_index, document)
    assert stored["title"] == "B"
    assert stored["summary"] == "written by the summarizer"
    assert stored["summary_status"] == "generated"
    assert call_count(search_index, ops.REPLACE) == 2
    assert call_count(search_index, ops.FETCH) == 3  # 初回 + 初回の登録 + 読み直し


def test_write_keeps_a_newer_last_seen_at_written_by_a_concurrent_update(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-20(a): `last_seen_at` の Update が先に入ると、PUT は読み直して新しい値を保つ。"""
    document = make_document(text="old text")
    register_one(registrar, document)
    search_index.behavior.before(
        ops.REPLACE,
        lambda: write_other_changes(
            search_index, document, last_seen_at="2026-11-10T00:00:00.000Z"
        ),
    )

    register_one(registrar, make_document(text="new text"))

    stored = stored_document(search_index, document)
    assert stored["content"] == "new text"
    assert stored["last_seen_at"] == "2026-11-10T00:00:00.000Z"


def test_reread_that_finds_the_change_already_applied_becomes_unchanged(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """読み直した文書がすでに同じ内容なら、変更なしとして書かない。"""
    document = make_document()
    register_one(registrar, document)
    changed = replace(document, title="B")
    search_index.behavior.before(
        ops.REPLACE, lambda: write_other_changes(search_index, document, title="B")
    )

    outcome = register_one(registrar, changed)

    assert outcome.change is Change.UNCHANGED
    assert call_count(search_index, ops.REPLACE) == 1


# --- C-18b: 読み直しの上限 ---


def test_conflicts_up_to_the_reread_limit_still_succeed(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    document = make_document(text="old text")
    register_one(registrar, document)
    search_index.behavior.inject(ops.REPLACE, Conflict(), times=MAX_REREADS)

    outcome = register_one(registrar, make_document(text="new text"))

    assert outcome.change is Change.UPDATED
    assert call_count(search_index, ops.REPLACE) == MAX_REREADS + 1


def test_conflicts_beyond_the_reread_limit_fail_with_a_retryable_write_conflict(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-18b: 上限を超えたら、文書は変わらず `write_conflict`(Crawler が再送する。K51)。"""
    document = make_document(text="old text")
    register_one(registrar, document)
    before = stored_document(search_index, document)
    search_index.behavior.inject(ops.REPLACE, Conflict(), times=MAX_REREADS + 1)

    outcome = register_one(registrar, make_document(text="new text"))

    assert isinstance(outcome, DocumentFailed)
    assert outcome.failure_type is FailureType.WRITE_CONFLICT
    assert stored_document(search_index, document) == before
    assert call_count(search_index, ops.REPLACE) == MAX_REREADS + 1


def test_create_conflicts_beyond_the_reread_limit_also_fail(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    search_index.behavior.inject(ops.CREATE, Conflict(), times=MAX_REREADS + 1)
    # 読み直しで文書が見つかると別の経路になるため、読み出しも「文書なし」にする。
    search_index.behavior.inject(ops.FETCH, None, times=MAX_REREADS + 1)

    outcome = register_one(registrar, make_document())

    assert isinstance(outcome, DocumentFailed)
    assert outcome.failure_type is FailureType.WRITE_CONFLICT
    assert search_index.document_ids() == []


def test_a_write_conflict_does_not_stop_the_rest_of_the_batch(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    first, second = make_document("a.txt"), make_document("b.txt")
    search_index.behavior.inject(ops.CREATE, Conflict(), key=id_of(first), times=MAX_REREADS + 1)
    search_index.behavior.inject(ops.FETCH, None, key=id_of(first), times=MAX_REREADS + 1)

    outcomes = registrar.register(make_context(), [first, second])

    assert [type(outcome) for outcome in outcomes] == [DocumentFailed, DocumentRegistered]


def test_the_reread_limit_follows_the_configuration(
    make_registrar,
    registration_config: RegistrationConfig,
    search_index: InMemorySearchIndex,
) -> None:
    registrar = make_registrar(replace(registration_config, write_conflict_max_rereads=1))
    document = make_document(text="old text")
    register_one(registrar, document)
    search_index.behavior.inject(ops.REPLACE, Conflict(), times=None)

    outcome = register_one(registrar, make_document(text="new text"))

    assert isinstance(outcome, DocumentFailed)
    assert call_count(search_index, ops.REPLACE) == 2


# --- C-18c: 読んだあとに文書が削除された ---


@pytest.mark.parametrize("response_to_missing_document", [NotFound(), Conflict()], ids=str)
def test_document_deleted_after_the_read_is_registered_as_new(
    response_to_missing_document: NotFound | Conflict,
    registrar: DocumentRegistrar,
    search_index: InMemorySearchIndex,
) -> None:
    """C-18c: 読んだあとに文書が削除されたら、読み直して新規として `create` する(エラーにしない)。

    存在しない文書への `if_seq_no` 付き PUT の応答は実機で未確認(U-31(2))。404 相当でも 409 でも
    同じ結果になる。
    """
    document = make_document(text="old text")
    register_one(registrar, document)
    search_index.behavior.before(ops.REPLACE, lambda: search_index.seed_removal(id_of(document)))
    search_index.behavior.inject(ops.REPLACE, response_to_missing_document)

    outcome = register_one(registrar, make_document(text="new text"))

    assert outcome.change is Change.CREATED
    assert stored_document(search_index, document)["content"] == "new text"


def test_document_deleted_before_the_last_seen_completion_is_registered_as_new(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """(b) の補完 Update が文書なしになったら、読み直して新規として扱う。"""
    document = make_document()
    register_one(registrar, document)
    write_other_changes(search_index, document, last_seen_at="2026-11-01T00:00:00.000Z")
    search_index.behavior.before(
        ops.RAISE_LAST_SEEN_AT, lambda: search_index.seed_removal(id_of(document))
    )

    outcome = register_one(registrar, document)

    assert outcome.change is Change.CREATED
    assert stored_document(search_index, document)["last_seen_at"] == CRAWL_STARTED_AT_TEXT


# --- C-7: 初回作成の競合 ---


def test_create_race_loser_rereads_the_existing_document_and_writes_nothing_more(
    make_registrar, registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """C-7: 2 つの登録が「文書なし」を読んだあと、片方の `create` が先に入る。

    もう一方は `create` が 409 になり、読み直して既存の文書として扱う(同じ内容なら書かない)。
    先に入る側は、別の Indexer を想定して別のソース単位ロックで動かす(同じロックでは直列になる)。
    """
    other_registrar = make_registrar(locks=SourceLocks())
    document = make_document()
    search_index.behavior.before(
        ops.CREATE, lambda: other_registrar.register(make_context(), [document])
    )

    outcome = register_one(registrar, document)

    assert outcome.change is Change.UNCHANGED
    assert call_count(search_index, ops.CREATE) == 2  # 先に入った側(成功)と、負けた側(409)
    assert search_index.document_ids() == [id_of(document)]
    assert call_count(search_index, ops.REPLACE) == 0


def test_create_race_loser_updates_when_the_winner_wrote_different_content(
    make_registrar, registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    other_registrar = make_registrar(locks=SourceLocks())
    search_index.behavior.before(
        ops.CREATE,
        lambda: other_registrar.register(make_context(), [make_document(text="the winner")]),
    )

    outcome = register_one(registrar, make_document(text="the loser"))

    assert outcome.change is Change.UPDATED
    assert stored_document(search_index, "docs/a.txt")["content"] == "the loser"


# --- 0005 の持ち越し: タイムアウト再送で、1 回目が実は成功していた ---


def test_resend_during_the_first_request_waits_for_it_and_then_sees_it_unchanged(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """現実の再送: 1 回目が処理中のうちに、Crawler が同じバッチを再送する。

    ソース単位のロックで、再送は 1 回目が終わるまで待たされる。待ったあとの再送は、
    1 回目の書き込みを読んで変更なしになる。`create` は 1 回だけで、409 は起きない
    (下の注入のテストは、防御の確認)。
    """
    document = make_document()
    resend_started = threading.Event()
    resend_done = threading.Event()
    resend_outcomes: list[DocumentOutcome] = []

    def resend() -> None:
        resend_started.set()
        resend_outcomes.append(register_one(registrar, document))
        resend_done.set()

    resend_thread = threading.Thread(target=resend, daemon=True)
    resend_was_blocked: list[bool] = []

    def resend_while_the_first_request_is_writing() -> None:
        resend_thread.start()
        assert resend_started.wait(JOIN_TIMEOUT_SECONDS)
        resend_was_blocked.append(not resend_done.wait(BLOCKED_PROBE_SECONDS))

    search_index.behavior.before(ops.CREATE, resend_while_the_first_request_is_writing)

    first = register_one(registrar, document)

    assert resend_was_blocked == [True]
    assert resend_done.wait(JOIN_TIMEOUT_SECONDS)
    resend_thread.join(JOIN_TIMEOUT_SECONDS)
    assert first == DocumentRegistered("docs/a.txt", id_of(document), Change.CREATED, False)
    assert resend_outcomes == [
        DocumentRegistered("docs/a.txt", id_of(document), Change.UNCHANGED, False)
    ]
    assert call_count(search_index, ops.CREATE) == 1
    assert call_count(search_index, ops.REPLACE) == 0


def test_resend_after_a_lost_response_succeeds_when_create_returns_409(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """Crawler が応答を受け取れず再送したとき、1 回目の `op_type=create` は成功済みだった。

    再送の読み出しが「文書なし」(1 回目の書き込みがまだ見えない)を返すと、`create` は 409 になる。
    読み直すと自分が書いた内容があるので、変更なしと判定して成立する(`created` が
    `unchanged` と返りうることは設計上の既知の挙動。arch 4.3 の `change` の区分)。
    """
    document = make_document()
    register_one(registrar, document)  # 1 回目(応答は Crawler に届かなかった)
    search_index.behavior.inject(ops.FETCH, None, key=id_of(document))  # 再送の最初の読み出し

    outcome = register_one(registrar, document)

    assert outcome == DocumentRegistered("docs/a.txt", id_of(document), Change.UNCHANGED, False)
    assert call_count(search_index, ops.CREATE) == 2
    assert call_count(search_index, ops.REPLACE) == 0


def test_resend_after_a_lost_response_succeeds_when_the_conditional_put_returns_409(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    """同じ再送で、`if_seq_no` 付きの PUT が 409 になる場合(版が古い読み出しを使った)。"""
    original = make_document(text="old text")
    register_one(registrar, original)
    stale_read = search_index.fetch(id_of(original))
    changed = make_document(text="new text")
    register_one(registrar, changed)  # 1 回目(応答は届かなかった)。版が進む
    search_index.behavior.inject(ops.FETCH, stale_read, key=id_of(changed))

    outcome = register_one(registrar, changed)

    assert outcome.change is Change.UNCHANGED
    assert call_count(search_index, ops.REPLACE) == 2  # 1 回目の成功と、再送の 409
    assert stored_document(search_index, changed)["content"] == "new text"


# --- 全体異常 ---


def test_whole_index_failure_during_a_write_propagates(
    registrar: DocumentRegistrar, search_index: InMemorySearchIndex
) -> None:
    search_index.behavior.inject(ops.CREATE, OpenSearchUnavailableError("http_429"))

    with pytest.raises(UnavailableError):
        register_one(registrar, make_document())

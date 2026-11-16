"""全 Connector 実装が通る共通の契約テスト(interface 10章。CI-P-13)。

FS Connector と偽の Connector(`tests/fakes/fake_connector.py`)の両方に、同じテストを流す。
偽の Connector が契約を守っていることで、`documents`・`crawl` のテストが偽の Connector に
頼れる。FS 固有の観点(エラー分類など)は `tests/connectors/filesystem/` にある。

対応する観点: #5(`content_hash`・`size`)、#6(列挙の終端)、#9(取得)、#8(ストリーミング。FS)、
#10・#11 の一部。#1〜#4・#7 は `tests/documents/`。
"""

import gc
import hashlib
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from loreley_crawler.connectors.interface import (
    Completed,
    Connector,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
)
from loreley_crawler.documents import DocumentFetcher, DocumentsSettings
from tests.connectors.filesystem.support import create_connector, drain, write_file
from tests.fakes.fake_connector import FakeConnector
from tests.fakes.fake_fs_ops import SCANDIR, ScriptedFsOps

CONTENTS = {"a.txt": b"alpha", "docs/b.md": b"# beta", "empty.txt": b""}


@dataclass(frozen=True)
class ContractSubject:
    name: str
    # `CONTENTS` の文書を列挙・取得できる Connector。
    create_connector: Callable[[], Connector]
    # 列挙が途中で失敗する(`Failed`)Connector。
    create_failing_connector: Callable[[], Connector]


def file_system_subject(tmp_path: Path) -> ContractSubject:
    for name, content in CONTENTS.items():
        write_file(tmp_path, name, content)

    def failing() -> Connector:
        fs = ScriptedFsOps()
        connector = create_connector(tmp_path, fs)
        fs.behavior.inject(SCANDIR, PermissionError(13, "denied"), key=str(tmp_path / "docs"))
        return connector

    return ContractSubject("file_system", lambda: create_connector(tmp_path), failing)


def fake_subject() -> ContractSubject:
    failure = ConnectorError.of(ErrorCategory.ENUMERATION_INCOMPLETE, "unreadable")
    return ContractSubject(
        "fake",
        lambda: FakeConnector.of(CONTENTS),
        lambda: FakeConnector(
            [DocumentRef("a.txt", "a.txt"), failure],
            {"a.txt": FakeConnector.of(CONTENTS).documents["a.txt"]},
        ),
    )


@pytest.fixture(params=["file_system", "fake"])
def subject(request: pytest.FixtureRequest, tmp_path: Path) -> ContractSubject:
    if request.param == "file_system":
        return file_system_subject(tmp_path)
    return fake_subject()


def external_ids(refs: list[DocumentRef]) -> set[str]:
    return {ref.external_id for ref in refs}


# --- #6 列挙の終端 ---


def test_the_enumeration_returns_every_document_and_then_completes(
    subject: ContractSubject,
) -> None:
    refs, terminal = drain(subject.create_connector().enumerate())

    assert external_ids(refs) == set(CONTENTS)
    assert terminal == Completed()


def test_next_after_completed_keeps_returning_completed(subject: ContractSubject) -> None:
    stream = subject.create_connector().enumerate()
    drain(stream)

    assert stream.next() == Completed()


def test_an_enumeration_that_cannot_list_everything_fails_instead_of_completing(
    subject: ContractSubject,
) -> None:
    stream = subject.create_failing_connector().enumerate()

    _, terminal = drain(stream)

    assert isinstance(terminal, ConnectorError)
    assert terminal.category is ErrorCategory.ENUMERATION_INCOMPLETE
    # 失敗の後に続きを求めても、完了にはならない。
    with pytest.raises(ConnectorError):
        stream.next()


def test_closing_midway_never_turns_into_completion(subject: ContractSubject) -> None:
    stream = subject.create_connector().enumerate()
    first = stream.next()

    stream.close()

    assert isinstance(first, DocumentRef)
    with pytest.raises(RuntimeError):
        stream.next()


def test_the_connector_fetches_after_the_stream_is_closed_and_enumerates_again(
    subject: ContractSubject,
) -> None:
    connector = subject.create_connector()
    stream = connector.enumerate()
    ref = stream.next()
    stream.close()
    assert isinstance(ref, DocumentRef)

    assert connector.fetch(ref, 1024).content == CONTENTS[ref.external_id]
    refs, terminal = drain(connector.enumerate())
    assert (external_ids(refs), terminal) == (set(CONTENTS), Completed())


# --- #9 取得 / #5 content_hash・size ---


def test_the_same_ref_can_be_fetched_twice(subject: ContractSubject) -> None:
    connector = subject.create_connector()
    refs, _ = drain(connector.enumerate())

    for ref in refs:
        first = connector.fetch(ref, 1024)
        second = connector.fetch(ref, 1024)
        assert first == second
        assert first.content == CONTENTS[ref.external_id]


def test_content_hash_and_size_come_from_the_fetched_bytes(subject: ContractSubject) -> None:
    connector = subject.create_connector()
    fetcher = DocumentFetcher(connector, settings=DocumentsSettings(max_raw_bytes=1024))
    refs, _ = drain(connector.enumerate())

    for ref in refs:
        prepared = fetcher.fetch(ref)
        content = CONTENTS[ref.external_id]
        assert prepared.content_hash == hashlib.sha256(content).hexdigest()
        assert prepared.size == len(content)


def test_a_document_over_the_limit_is_oversize(subject: ContractSubject) -> None:
    connector = subject.create_connector()
    ref = DocumentRef("a.txt", "a.txt")

    assert connector.fetch(ref, len(CONTENTS["a.txt"])).content == CONTENTS["a.txt"]
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(ref, len(CONTENTS["a.txt"]) - 1)

    assert exc_info.value.category is ErrorCategory.OVERSIZE


def test_the_metadata_has_the_required_fields(subject: ContractSubject) -> None:
    connector = subject.create_connector()

    metadata = connector.fetch(DocumentRef("a.txt", "a.txt"), 1024).metadata

    assert metadata.title
    assert metadata.mime_type
    assert metadata.source_updated_at.utcoffset() is not None


# --- #8 ストリーミング(FS) ---


def test_the_file_system_connector_does_not_keep_the_refs_it_returned(tmp_path: Path) -> None:
    for index in range(300):
        write_file(tmp_path, f"dir{index % 7}/{index}.txt")
    stream = create_connector(tmp_path).enumerate()
    returned: list[weakref.ref[DocumentRef]] = []
    while True:
        item = stream.next()
        if isinstance(item, Completed):
            break
        returned.append(weakref.ref(item))
        del item

    gc.collect()

    # 返した `DocumentRef` を Connector が溜め込んでいれば、件数に比例して残る。
    assert len(returned) == 300
    assert sum(1 for reference in returned if reference() is not None) == 0

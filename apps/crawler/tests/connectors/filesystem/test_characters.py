"""ファイル名・文字の扱い(FS 設計書 8章。10章 #18・#19)。

Linux 専用の部分(非 UTF-8 の名前、NFC と NFD・大文字小文字だけが違う名前の併存)は、
作れない FS(macOS の APFS など)では skip する。OS の名前ではなく、実際に作れるかで判定する。
共通処理との組み合わせ(ID 用エスケープ、衝突の検出)も確かめる。
"""

import os
import sys
import unicodedata
from pathlib import Path

import pytest

from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
)
from loreley_crawler.documents import (
    DocumentEnumeration,
    DocumentsSettings,
    EnumeratedDocument,
    InvalidExternalId,
    apply_external_id_rules,
)
from tests.connectors.filesystem.support import (
    SOURCE_ID,
    create_connector,
    create_names_or_skip,
    drain,
    enumerate_ids,
    skip_unless_listed,
    write_file,
)
from tests.unicode_samples import GA_NFC, GA_NFD

REPLACEMENT = chr(0xFFFD)
NFD_DIRECTORY = GA_NFD
NFC_DIRECTORY = GA_NFC
NFD_NAME = f"{NFD_DIRECTORY}.txt"
NFC_NAME = f"{NFC_DIRECTORY}.txt"


def test_the_filesystem_encoding_is_utf8() -> None:
    assert sys.getfilesystemencoding() == "utf-8"
    assert sys.getfilesystemencodeerrors() == "surrogateescape"


# --- #18 文字(Linux のみ) ---


def test_a_non_utf8_name_is_returned_as_surrogateescape_and_can_be_fetched(
    tmp_path: Path,
) -> None:
    raw_name = b"\x82\xa0.txt"  # CP932 の「あ」
    create_names_or_skip(tmp_path, [raw_name], what="a non-UTF-8 name")
    (tmp_path / os.fsdecode(raw_name)).write_bytes(b"cp932 name")
    connector = create_connector(tmp_path)

    refs, terminal = drain(connector.enumerate())

    assert terminal == Completed()
    [ref] = refs
    assert ref.external_id == "\udc82\udca0.txt"
    assert os.fsencode(ref.external_id) == raw_name  # 元のバイト列に戻せる
    assert connector.fetch(ref, 100).content == b"cp932 name"
    # `external_id` は共通処理が ID 用エスケープする(孤立サロゲートを Indexer に送らない)。
    assert apply_external_id_rules(ref.external_id) == f"{REPLACEMENT}uDC82{REPLACEMENT}uDCA0.txt"


# --- #19 `\`・改行・タブ・NFD ---


def test_names_with_a_backslash_newline_and_tab_are_returned_and_fetched(tmp_path: Path) -> None:
    names = ["a\\b.txt", "line\nbreak.txt", "tab\there.txt"]
    for name in names:
        write_file(tmp_path, name, name.encode())
    connector = create_connector(tmp_path)

    assert enumerate_ids(connector) == set(names)  # 加工せず返す
    for name in names:
        assert connector.fetch(DocumentRef(name, name), 100).content == name.encode()


def test_an_nfd_name_is_returned_unchanged_and_its_title_and_path_are_nfc(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, f"{NFD_DIRECTORY}/{NFD_NAME}")
    skip_unless_listed(tmp_path / NFD_DIRECTORY, NFD_NAME)
    connector = create_connector(tmp_path)
    refs, _ = drain(connector.enumerate())
    [ref] = refs

    metadata = connector.fetch(ref, 100).metadata

    # `external_id` は加工しない(NFC にするのは共通処理)。
    assert ref.external_id == f"{NFD_DIRECTORY}/{NFD_NAME}"
    assert apply_external_id_rules(ref.external_id) == f"{NFC_DIRECTORY}/{NFC_NAME}"
    assert metadata.title == NFC_NAME
    assert metadata.path == f"{NFC_DIRECTORY}/{NFC_NAME}"
    assert unicodedata.is_normalized("NFC", metadata.path)


def collect_through_common_processing(connector_root: Path) -> list[object]:
    connector = create_connector(connector_root)
    enumeration = DocumentEnumeration(
        connector.enumerate(), source_id=SOURCE_ID, settings=DocumentsSettings()
    )
    results: list[object] = []
    while True:
        result = enumeration.next()
        if isinstance(result, Completed):
            return results
        results.append(result)


def test_a_backslash_name_and_a_nested_file_with_the_same_id_are_detected_as_a_collision(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "a\\b.txt", b"flat")
    write_file(tmp_path, "a/b.txt", b"nested")

    with pytest.raises(ConnectorError) as exc_info:
        collect_through_common_processing(tmp_path)

    assert exc_info.value.category is ErrorCategory.EXTERNAL_ID_COLLISION


def test_a_name_starting_with_a_backslash_is_an_invalid_external_id(tmp_path: Path) -> None:
    # `\` の置換後に先頭が `/` になる(先頭の `/` は除去しない)。
    write_file(tmp_path, "\\leading.txt", b"x")
    write_file(tmp_path, "ok.txt", b"x")

    results = collect_through_common_processing(tmp_path)

    # 順序は規定しないので、種類ごとに確かめる。
    valid = [r for r in results if isinstance(r, EnumeratedDocument)]
    invalid = [r for r in results if isinstance(r, InvalidExternalId)]
    assert [r.external_id for r in valid] == ["ok.txt"]
    assert [r.error.category for r in invalid] == [ErrorCategory.INVALID_EXTERNAL_ID]
    assert len(results) == 2


def test_names_that_differ_only_by_case_are_different_documents(tmp_path: Path) -> None:
    create_names_or_skip(tmp_path, [b"Case.txt", b"case.txt"], what="names differing only by case")

    assert enumerate_ids(create_connector(tmp_path)) == {"Case.txt", "case.txt"}


def test_nfc_and_nfd_names_that_coexist_are_detected_as_a_collision(tmp_path: Path) -> None:
    create_names_or_skip(
        tmp_path, [NFC_NAME.encode(), NFD_NAME.encode()], what="NFC and NFD names together"
    )

    with pytest.raises(ConnectorError) as exc_info:
        collect_through_common_processing(tmp_path)

    assert exc_info.value.category is ErrorCategory.EXTERNAL_ID_COLLISION


# --- 日本語・絵文字の名前 ---


def test_japanese_nfc_names_are_enumerated_and_fetched_in_a_normal_way(tmp_path: Path) -> None:
    names = ["資料/議事録.md", "日本語のファイル名.txt", f"資料/{NFC_NAME}"]
    for name in names:
        write_file(tmp_path, name, name.encode())
    connector = create_connector(tmp_path)

    assert enumerate_ids(connector) == set(names)
    fetched = connector.fetch(DocumentRef("資料/議事録.md", "資料/議事録.md"), 100)
    assert fetched.content == "資料/議事録.md".encode()
    assert fetched.metadata.title == "議事録.md"
    assert fetched.metadata.path == "資料/議事録.md"
    assert fetched.metadata.mime_type == "text/markdown"


def test_a_name_with_a_four_byte_character_is_not_mistaken_for_lone_surrogates(
    tmp_path: Path,
) -> None:
    name = "メモ\U0001f600.txt"  # 絵文字は 1 つのコードポイント(UTF-16 では 2 つの単位)
    write_file(tmp_path, name, b"emoji")

    results = collect_through_common_processing(tmp_path)

    [document] = results
    assert isinstance(document, EnumeratedDocument)
    assert document.external_id == name  # ID 用エスケープされない
    assert REPLACEMENT not in document.external_id
    fetched = create_connector(tmp_path).fetch(document.ref, 100)
    assert fetched.metadata.title == name

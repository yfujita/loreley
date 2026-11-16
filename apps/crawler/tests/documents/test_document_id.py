"""`document_id` の算出関数とテストベクタ(interface 5.2・10章 #1。architecture 12章 #1)。

テストベクタは、`document_id_vectors.json`(interface 5.2 の全行。出典つき)。共通処理を通さず
算出関数へ直接入力する行を含む。
"""

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory
from loreley_crawler.documents import apply_external_id_rules, compute_document_id
from tests.unicode_samples import GA_NFC, GA_NFD

VECTOR_FILE = Path(__file__).parent / "document_id_vectors.json"

# interface 5.2 の表の行数(行を足す・減らすときは、設計書の改版と合わせてここも更新する)。
DESIGN_TABLE_ROWS = 8


def load_cases() -> list[tuple[str, str, str, bool]]:
    """(source_id, external_id, 期待する document_id, 共通処理を通せるか)。入力ごとに 1 件。"""
    document = json.loads(VECTOR_FILE.read_text(encoding="utf-8"))
    return [
        (
            vector["source_id"],
            external_id,
            vector["document_id"],
            vector["through_common_processing"],
        )
        for vector in document["vectors"]
        for external_id in vector["external_ids"]
    ]


def load_vectors() -> list[dict[str, Any]]:
    return json.loads(VECTOR_FILE.read_text(encoding="utf-8"))["vectors"]


CASES = load_cases()


def test_the_vector_file_has_every_row_of_the_design_table_with_its_origin() -> None:
    document = json.loads(VECTOR_FILE.read_text(encoding="utf-8"))

    assert len(document["vectors"]) == DESIGN_TABLE_ROWS
    assert document["origin"]
    assert document["verification"]
    for vector in document["vectors"]:
        assert vector["origin"]
        assert len(vector["document_id"]) == 64
        assert vector["document_id"] == vector["document_id"].lower()


def test_the_vector_file_contains_the_inputs_that_the_design_row_names() -> None:
    # 「NFD の入力でも同じ」「`a\b.txt` と `a/b.txt`(両方同じ)」の行が、複数の入力を持つこと。
    inputs_by_id = {v["document_id"]: v["external_ids"] for v in load_vectors()}

    nfc_row = inputs_by_id["61333b3265b1d26d226ced9296e0e072de607e1e7a09f84ff797de59bfb2738f"]
    assert len(nfc_row) == 2
    assert unicodedata.is_normalized("NFC", nfc_row[0])
    assert not unicodedata.is_normalized("NFC", nfc_row[1])  # エディタに正規化されていない
    assert unicodedata.normalize("NFC", nfc_row[1]) == nfc_row[0]
    assert inputs_by_id["acf087b56a18acd68b1b30209882aaa1a42c6cf2000f423c8982a227ec80f83d"] == [
        "a\\b.txt",
        "a/b.txt",
    ]
    bypass = [v for v in load_vectors() if not v["through_common_processing"]]
    assert [v["external_ids"] for v in bypass] == [["/docs/guide.md"]]


@pytest.mark.parametrize(
    ("source_id", "external_id", "expected", "through_common_processing"), CASES
)
def test_the_function_matches_every_vector_when_given_the_input_directly(
    source_id: str, external_id: str, expected: str, through_common_processing: bool
) -> None:
    assert compute_document_id(source_id, external_id) == expected


@pytest.mark.parametrize(
    ("source_id", "external_id", "expected", "through_common_processing"),
    [case for case in CASES if case[3]],
)
def test_the_function_matches_every_vector_after_the_common_processing(
    source_id: str, external_id: str, expected: str, through_common_processing: bool
) -> None:
    final_form = apply_external_id_rules(external_id)

    assert compute_document_id(source_id, final_form) == expected


@pytest.mark.parametrize(
    ("source_id", "external_id", "expected", "through_common_processing"),
    [case for case in CASES if not case[3]],
)
def test_a_row_that_bypasses_the_common_processing_is_rejected_by_it(
    source_id: str, external_id: str, expected: str, through_common_processing: bool
) -> None:
    with pytest.raises(ConnectorError) as exc_info:
        apply_external_id_rules(external_id)

    assert exc_info.value.category is ErrorCategory.INVALID_EXTERNAL_ID


def test_a_leading_slash_makes_a_different_id() -> None:
    assert compute_document_id("src-fs", "/docs/guide.md") != compute_document_id(
        "src-fs", "docs/guide.md"
    )


def test_the_id_is_sha256_of_source_id_nul_external_id_in_lowercase_hex() -> None:
    document_id = compute_document_id("src", "a/b.txt")

    assert document_id == hashlib.sha256(b"src\x00a/b.txt").hexdigest()
    assert len(document_id) == 64
    assert document_id == document_id.lower()


def test_the_source_id_is_not_normalized() -> None:
    nfd_source = GA_NFD
    nfc_source = GA_NFC

    assert compute_document_id(nfd_source, "a") != compute_document_id(nfc_source, "a")
    assert (
        compute_document_id(nfd_source, "a")
        == hashlib.sha256(nfd_source.encode() + b"\x00a").hexdigest()
    )


def test_the_normalization_is_idempotent() -> None:
    once = apply_external_id_rules(f"資料/{GA_NFD}.txt")

    assert compute_document_id("s", once) == compute_document_id("s", f"資料/{GA_NFD}.txt")


def test_the_nul_separator_keeps_different_pairs_apart() -> None:
    assert compute_document_id("a", "b") != compute_document_id("ab", "")
    assert compute_document_id("a", "bc") != compute_document_id("ab", "c")


SECRET_SOURCE_ID = "SRC-SENTINEL"
SECRET_EXTERNAL_ID = "EXT-SENTINEL"


@pytest.mark.parametrize(
    ("source_id", "external_id"),
    [
        (f"{SECRET_SOURCE_ID}\x00", SECRET_EXTERNAL_ID),
        (SECRET_SOURCE_ID, f"{SECRET_EXTERNAL_ID}\x00"),
        (SECRET_SOURCE_ID, "\x00"),
    ],
)
def test_nul_in_either_part_is_rejected_without_echoing_the_input(
    source_id: str, external_id: str
) -> None:
    with pytest.raises(ValueError, match="NUL") as exc_info:
        compute_document_id(source_id, external_id)

    assert "SENTINEL" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("source_id", "external_id"),
    [(SECRET_SOURCE_ID, f"{SECRET_EXTERNAL_ID}\udc80"), (f"{SECRET_SOURCE_ID}\ud800", "a")],
)
def test_a_lone_surrogate_is_rejected_without_echoing_the_input(
    source_id: str, external_id: str
) -> None:
    with pytest.raises(ValueError, match="valid Unicode") as exc_info:
        compute_document_id(source_id, external_id)

    assert "SENTINEL" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True

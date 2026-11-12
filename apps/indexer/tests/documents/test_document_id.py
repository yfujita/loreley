import hashlib
import unicodedata

import pytest

from loreley_indexer.documents.document_id import compute_document_id, normalize_external_id

# api 4.3 の応答例(source_id `src-docs`)の document_id。
API_EXAMPLE_VECTORS = [
    ("src-docs", "page-10023", "6b5851d90534fc00e388eeb8bd8c79ae48b8bf5c58e4fb0191e708afa28674d7"),
    ("src-docs", "page-10024", "7f2216b2a91e74fe53ce071ed0bd8dcebccaa904f9a8d8004f592b0a4210a9c5"),
    ("src-docs", "page-10025", "48ea91b73f76334d8cf88f6a77438e740ba9d54a338970ad1433aa2f504c2c40"),
]


@pytest.mark.parametrize(("source_id", "external_id", "expected"), API_EXAMPLE_VECTORS)
def test_document_id_matches_the_api_example_vectors(
    source_id: str, external_id: str, expected: str
) -> None:
    assert compute_document_id(source_id, external_id) == expected


def test_document_id_is_sha256_of_source_id_nul_external_id_in_lowercase_hex() -> None:
    document_id = compute_document_id("src", "a/b.txt")
    assert document_id == hashlib.sha256(b"src\x00a/b.txt").hexdigest()
    assert len(document_id) == 64
    assert document_id == document_id.lower()


def test_same_input_gives_the_same_id() -> None:
    assert compute_document_id("src", "a/b.txt") == compute_document_id("src", "a/b.txt")


def test_nul_separator_keeps_different_pairs_apart() -> None:
    # 区切りがなければ、どちらも連結すると "ab" になる組。
    assert compute_document_id("a", "b") != compute_document_id("ab", "")
    assert compute_document_id("a", "bc") != compute_document_id("ab", "c")


SOURCE_ID_SENTINEL = "SRC-SENTINEL"
EXTERNAL_ID_SENTINEL = "EXT-SENTINEL"


@pytest.mark.parametrize(
    ("source_id", "external_id"),
    [
        (f"{SOURCE_ID_SENTINEL}\x00", EXTERNAL_ID_SENTINEL),
        (SOURCE_ID_SENTINEL, f"{EXTERNAL_ID_SENTINEL}\x00"),
        (SOURCE_ID_SENTINEL, "\x00"),
    ],
    ids=["nul_in_source_id", "nul_in_external_id", "nul_only"],
)
def test_nul_in_either_part_is_rejected_without_echoing_the_input(
    source_id: str, external_id: str
) -> None:
    with pytest.raises(ValueError, match="NUL") as exc_info:
        compute_document_id(source_id, external_id)

    message = str(exc_info.value)
    assert SOURCE_ID_SENTINEL not in message
    assert EXTERNAL_ID_SENTINEL not in message


@pytest.mark.parametrize(
    ("source_id", "external_id"),
    [
        (f"{SOURCE_ID_SENTINEL}\ud800", EXTERNAL_ID_SENTINEL),
        (SOURCE_ID_SENTINEL, f"{EXTERNAL_ID_SENTINEL}\udfff"),
    ],
    ids=["lone_surrogate_in_source_id", "lone_surrogate_in_external_id"],
)
def test_lone_surrogate_is_rejected_as_a_plain_value_error_without_echoing_the_input(
    source_id: str, external_id: str
) -> None:
    """孤立サロゲートは UTF-8 にできない。`UnicodeEncodeError` にせず、固定の文言にする。"""
    with pytest.raises(ValueError, match="valid Unicode") as exc_info:
        compute_document_id(source_id, external_id)

    assert exc_info.type is ValueError
    message = str(exc_info.value)
    assert SOURCE_ID_SENTINEL not in message
    assert EXTERNAL_ID_SENTINEL not in message


def test_external_id_is_normalized_to_nfc_before_hashing() -> None:
    nfc = unicodedata.normalize("NFC", "資料/がぎ.txt")
    nfd = unicodedata.normalize("NFD", nfc)
    assert nfc != nfd
    assert compute_document_id("src", nfd) == compute_document_id("src", nfc)


def test_path_separators_are_unified_to_slash() -> None:
    assert compute_document_id("src", "dir\\sub\\file.txt") == compute_document_id(
        "src", "dir/sub/file.txt"
    )


def test_leading_slash_is_kept_because_it_is_an_input_precondition_not_a_rule() -> None:
    # 「先頭に `/` を付けない」は入力の前提。Indexer が除くと、Crawler が算出した ID とずれる。
    assert normalize_external_id("/dir/file.txt") == "/dir/file.txt"
    assert normalize_external_id("\\dir\\file.txt") == "/dir/file.txt"
    assert compute_document_id("src", "/dir/file.txt") != compute_document_id("src", "dir/file.txt")


def test_case_is_preserved() -> None:
    assert compute_document_id("src", "Readme.md") != compute_document_id("src", "readme.md")


def test_source_id_is_not_normalized() -> None:
    nfc = unicodedata.normalize("NFC", "がぎ")
    nfd = unicodedata.normalize("NFD", nfc)
    assert compute_document_id(nfc, "a") != compute_document_id(nfd, "a")


def test_different_sources_give_different_ids_for_the_same_external_id() -> None:
    assert compute_document_id("src-1", "a.txt") != compute_document_id("src-2", "a.txt")

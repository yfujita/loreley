"""`unavailable` の組み立て(B 2.2。AAM-P-29)。最上位用と一覧の行用を区別する。"""

import pytest

from loreley_api.admin.base.codes import UnavailableReason
from loreley_api.admin.failures import row_unavailable, top_level_unavailable

STORE = UnavailableReason.STORE_UNAVAILABLE
TIMEOUT = UnavailableReason.TIMEOUT
SEARCH = UnavailableReason.SEARCH_INDEX_UNAVAILABLE


def test_the_top_level_has_the_full_paths_as_keys() -> None:
    result = top_level_unavailable({"index.document_count": SEARCH, "deletion.current": TIMEOUT})

    assert result == {
        "index.document_count": "search_index_unavailable",
        "deletion.current": "timeout",
    }


def test_the_top_level_is_an_empty_object_when_nothing_failed() -> None:
    assert top_level_unavailable({}) == {}


def test_the_top_level_is_a_copy() -> None:
    reasons = {"lock": STORE}

    result = top_level_unavailable(reasons)
    result["other"] = TIMEOUT

    assert reasons == {"lock": STORE}


def test_each_row_has_its_own_relative_keys_and_a_clean_row_has_an_empty_object() -> None:
    """EP-01: 未実行の source-a(キーなし)と、読み取りに失敗した source-b を区別できる。"""
    result = row_unavailable(
        ["source-a", "source-b", "source-c"],
        {"source-b": {"last_crawl.stalled": STORE}, "source-c": {"document_count": SEARCH}},
    )

    assert result == {
        "source-a": {},
        "source-b": {"last_crawl.stalled": "store_unavailable"},
        "source-c": {"document_count": "search_index_unavailable"},
    }


def test_the_rows_keep_the_order_of_the_ids() -> None:
    result = row_unavailable(["b", "a", "c"], {})

    assert list(result) == ["b", "a", "c"]


def test_no_rows_give_no_entries() -> None:
    assert row_unavailable([], {}) == {}


def test_a_failure_for_a_row_that_is_not_in_the_list_is_a_programming_error() -> None:
    with pytest.raises(ValueError, match="not in the list"):
        row_unavailable(["a"], {"b": {"last_crawl": STORE}})


@pytest.mark.parametrize("key", ["items[].stalled", "items[0].stalled"])
def test_the_items_array_form_of_a_key_is_never_built(key: str) -> None:
    with pytest.raises(ValueError, match="items"):
        top_level_unavailable({key: STORE})
    with pytest.raises(ValueError, match="items"):
        row_unavailable(["a"], {"a": {key: STORE}})

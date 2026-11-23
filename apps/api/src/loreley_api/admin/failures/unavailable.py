"""`unavailable` を組み立てる 1 か所(B 2.2。AAM-P-29)。

2 つの関数を区別する。キーの意味が違い、取り違えると画面が失敗を正しい行・項目に結び付けられない。
- `top_level_unavailable`: 単一の応答の最上位。キーは応答の項目の**正式なパス**
  (`index.document_count`、`deletion.current` など)。一覧の EP の最上位には、行に属さない項目
  (EP-11 の `tab_counts.<タブ>`)だけを渡す。
- `row_unavailable`: 一覧の行ごと。キーは**行の中の相対パス**(`last_crawl.stalled`・
  `existence` など)。失敗した行にだけキーを付け、失敗のない行は `{}`(常に存在する)。

`items[].…` 形式のキーは作らない(C 5.8)。
"""

from collections.abc import Iterable, Mapping

from loreley_api.admin.base.codes import UnavailableReason

_FORBIDDEN_KEY_PREFIX = "items["


def top_level_unavailable(
    reasons_by_path: Mapping[str, UnavailableReason],
) -> dict[str, UnavailableReason]:
    _check_keys(reasons_by_path)
    return dict(reasons_by_path)


def row_unavailable(
    row_ids: Iterable[str],
    reasons_by_row: Mapping[str, Mapping[str, UnavailableReason]],
) -> dict[str, dict[str, UnavailableReason]]:
    """`row_ids` の各行の `unavailable`。`reasons_by_row` にない行は `{}`。"""
    row_id_list = list(row_ids)
    unknown_rows = reasons_by_row.keys() - set(row_id_list)
    if unknown_rows:
        raise ValueError("reasons are given for a row that is not in the list")
    result: dict[str, dict[str, UnavailableReason]] = {}
    for row_id in row_id_list:
        reasons = reasons_by_row.get(row_id, {})
        _check_keys(reasons)
        result[row_id] = dict(reasons)
    return result


def _check_keys(reasons_by_path: Mapping[str, UnavailableReason]) -> None:
    if any(path.startswith(_FORBIDDEN_KEY_PREFIX) for path in reasons_by_path):
        raise ValueError("an unavailable key must not use the items[] form")

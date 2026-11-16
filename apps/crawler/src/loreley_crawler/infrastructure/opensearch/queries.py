"""呼び出し側が指定する検索条件と並べ替え。OpenSearch のクエリ DSL への変換はアダプタが行う。"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

FieldValue = str | bool | int


@dataclass(frozen=True)
class RecordFilter:
    """一覧・全件走査の条件(単純な条件のみ。architecture 3.1)。指定したものはすべて満たす(AND)。

    `term`・`terms` による絞り込みは、対象の項目が keyword(または整数・真偽値)であることが
    前提(マッピング案。architecture 3.1 の CA-P-49)。
    """

    equals: Mapping[str, FieldValue] = field(default_factory=dict)
    one_of: Mapping[str, Sequence[FieldValue]] = field(default_factory=dict)
    exists: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class SortKey:
    field_name: str
    descending: bool = False

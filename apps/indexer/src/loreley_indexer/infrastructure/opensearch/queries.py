"""呼び出し側が指定する検索条件。OpenSearch のクエリ DSL への変換はアダプタが行う。"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

FieldValue = str | bool | int


@dataclass(frozen=True)
class DocumentFilter:
    """検索インデックスの文書の絞り込み条件。指定した条件はすべて満たす(AND)。"""

    source_id: str | None = None
    last_seen_at_gte: datetime | None = None
    last_seen_at_lt: datetime | None = None
    summary_status: str | None = None


@dataclass(frozen=True)
class RecordFilter:
    """Store 層の一覧の条件(単純な条件のみ。arch 3.5)。すべて満たす(AND)。"""

    equals: Mapping[str, FieldValue] = field(default_factory=dict)
    one_of: Mapping[str, Sequence[FieldValue]] = field(default_factory=dict)
    exists: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class SortKey:
    field_name: str
    descending: bool = False

"""OpenSearch 操作の結果区分(module 4.4)。

区分は 5 つ: 成功 / 競合(409) / 文書なし / 文書固有の拒否 / OpenSearch 全体の異常。
全体異常だけは例外(`OpenSearchUnavailableError`)で伝播し、ほかは戻り値で返す。
全体異常は呼び出し側が個別に扱わず、api 層で 503 にするため。
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StoredDocument:
    """ID で取得した文書と、条件付き書き込みに使う版。"""

    id: str
    source: dict[str, Any]
    seq_no: int
    primary_term: int


@dataclass(frozen=True)
class Written:
    seq_no: int
    primary_term: int
    created: bool


@dataclass(frozen=True)
class Deleted:
    pass


@dataclass(frozen=True)
class Updated:
    """`last_seen_at` を新しい値で書いた。"""


@dataclass(frozen=True)
class Unchanged:
    """`last_seen_at` が現在値以上のため書かなかった(noop)。"""


@dataclass(frozen=True)
class Conflict:
    """409。`if_seq_no`/`if_primary_term` の不一致、または `op_type=create` の競合。"""


@dataclass(frozen=True)
class NotFound:
    """文書がない。索引自体の不在は含まない(それは全体異常)。"""


@dataclass(frozen=True)
class Rejected:
    """文書固有の拒否(マッピング違反など)。`error_type` は OpenSearch のエラー種別名のみ。

    OpenSearch の `reason` には文書の内容が含まれうるため、保持しない。
    """

    error_type: str


WriteOutcome = Written | Conflict | NotFound | Rejected
DeleteOutcome = Deleted | Conflict | NotFound | Rejected
LastSeenOutcome = Updated | Unchanged | Conflict | NotFound | Rejected


@dataclass(frozen=True)
class DeleteByQueryResult:
    deleted: int
    version_conflicts: int
    failure_count: int

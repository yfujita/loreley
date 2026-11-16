"""Repository の操作の結果区分(module 4.8。architecture 3.1)。

区分は 5 つ: 成功 / 競合(409) / 存在しない / すでに存在する / OpenSearch 全体の異常。
全体の異常だけは例外(`StoreUnavailableError`)で伝播し、ほかは戻り値で返す。呼び出し側が
個別に扱わず、リトライを尽くしたら `store_unavailable` にするため。

記録の中身(本文・設定・秘密)は結果に載せない。`StoredRecord.source` だけが記録の中身で、
呼び出し側(`sources`・`jobs`)が形式を解釈する。
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StoredRecord:
    """ID で取得した記録と、版条件つきの書き込みに使う版。"""

    id: str
    source: dict[str, Any]
    seq_no: int
    primary_term: int


@dataclass(frozen=True)
class Written:
    """書き込みの成功。次の版条件つきの書き込みには、この版を使う。"""

    seq_no: int
    primary_term: int


@dataclass(frozen=True)
class Deleted:
    """版条件つきの削除の成功。"""


@dataclass(frozen=True)
class Conflict:
    """409。`if_seq_no`/`if_primary_term` の不一致(読んだ後に別の書き込みが入った)。

    タイムアウト・接続断の後のリトライで返る場合は、最初の書き込みがすでに成功していた可能性が
    ある。記録を読み直して、所有者(`owner`・`job_id`)を確認してから判断すること。

    OpenSearch は、対象の記録がすでに消えていても、版条件つきの書き込みを 409 で拒否する
    (記録がない場合の `NotFound` と区別できない)。呼び出し側は、どちらも「条件が外れた」として
    読み直す。
    """


@dataclass(frozen=True)
class NotFound:
    """記録がない(404)。索引自体の不在は含まない(それは全体の異常)。"""


@dataclass(frozen=True)
class AlreadyExists:
    """`create`(`op_type=create`)で、同じ ID の記録がすでにある。

    タイムアウト・接続断の後のリトライで返る場合は、最初の `create` がすでに成功していた
    可能性がある(ロック文書など)。記録を読み直して、所有者(`owner`・`job_id`)が自分かを確認し、
    自分なら成功として扱うこと。
    """


@dataclass(frozen=True)
class BulkDeleteResult:
    """ID のバルク削除の結果。存在しない ID は成功とみなすので、`failed_ids` に入らない。

    `failed_ids` は一部の ID だけ失敗したもの(部分失敗)で、呼び出し側が、その ID だけを
    リトライする。空なら全件が成功(または、もともと存在しない)。
    """

    failed_ids: tuple[str, ...] = ()


CreateOutcome = Written | AlreadyExists
ReplaceOutcome = Written | Conflict | NotFound
DeleteOutcome = Deleted | Conflict | NotFound

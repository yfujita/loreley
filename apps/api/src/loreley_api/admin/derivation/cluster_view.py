"""`cluster.health`・`cat.*` の正規化(EP-12。C 3.4)。

値は応答のまま(文字列)受けて、整数・`None` への変換、`prirep`・`state` の正規化、`relocating` の
`node`、インデックスの補完・並び・切り詰めを行う。必須の項目がない・型が違うなど、応答が期待の形で
ないときは `ClusterShapeError`(固定の理由名だけを持つ。値は載せない)。
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from loreley_api.admin.base.constants import CLUSTER_INDEX_LIMIT
from loreley_api.admin.derivation.values import Document, read_str
from loreley_api.common.timestamps import format_instant

_DIGITS = re.compile(r"[0-9]+")
_RELOCATION_SEPARATOR = " -> "
_ROLE_BY_PRIREP = {"p": "primary", "r": "replica"}
_RELOCATING = "relocating"
_PRIMARY = "primary"
# 状態の悪い順(red → yellow → green)。それ以外(`null` を含む)は最後。
_STATUS_RANK = {"red": 0, "yellow": 1, "green": 2}
_OTHER_STATUS_RANK = len(_STATUS_RANK)


class ClusterShapeError(Exception):
    """応答が期待の形でない。`reason` は、ログに出してよい固定の名前。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ClusterInfo:
    name: str
    status: str
    node_count: int
    active_shards: int
    relocating_shards: int
    initializing_shards: int
    unassigned_shards: int


@dataclass(frozen=True)
class IndexInfo:
    name: str
    status: str | None
    document_count: int | None


@dataclass(frozen=True)
class ShardInfo:
    index: str
    shard: int
    role: str
    state: str
    node: str | None


@dataclass(frozen=True)
class ClusterView:
    fetched_at: str
    cluster: ClusterInfo
    nodes: tuple[str, ...]
    indices: tuple[IndexInfo, ...]
    shards: tuple[ShardInfo, ...]
    truncated: bool
    total_indices: int


def normalize_cluster(
    health: Document,
    indices: Sequence[Document],
    shards: Sequence[Document],
    nodes: Sequence[Document],
    *,
    now: datetime,
) -> ClusterView:
    shard_infos = [_read_shard(row) for row in shards]
    all_indices = sorted(
        _complete_indices([_read_index(row) for row in indices], shard_infos), key=_index_order
    )
    kept_indices = all_indices[:CLUSTER_INDEX_LIMIT]
    # シャードは、切り詰めた後のインデックスのものだけを返す。
    kept_names = {index.name for index in kept_indices}
    kept_shards = sorted(
        (shard for shard in shard_infos if shard.index in kept_names), key=_shard_order
    )
    return ClusterView(
        fetched_at=format_instant(now),
        cluster=_read_cluster(health),
        nodes=tuple(sorted(_read_node_name(row) for row in nodes)),
        indices=tuple(kept_indices),
        shards=tuple(kept_shards),
        truncated=len(all_indices) > CLUSTER_INDEX_LIMIT,
        total_indices=len(all_indices),
    )


def _read_cluster(health: Document) -> ClusterInfo:
    return ClusterInfo(
        name=_required_str(health.get("cluster_name"), "health_cluster_name"),
        status=_required_str(health.get("status"), "health_status").lower(),
        node_count=_required_count(health.get("number_of_nodes"), "health_number_of_nodes"),
        active_shards=_required_count(health.get("active_shards"), "health_active_shards"),
        relocating_shards=_required_count(
            health.get("relocating_shards"), "health_relocating_shards"
        ),
        initializing_shards=_required_count(
            health.get("initializing_shards"), "health_initializing_shards"
        ),
        unassigned_shards=_required_count(
            health.get("unassigned_shards"), "health_unassigned_shards"
        ),
    )


def _read_index(row: Document) -> IndexInfo:
    return IndexInfo(
        name=_required_str(row.get("index"), "indices_index"),
        status=_lower_or_none(row.get("health")),
        document_count=_cat_int(row.get("docs.count")),
    )


def _read_shard(row: Document) -> ShardInfo:
    index = _required_str(row.get("index"), "shards_index")
    shard = _cat_int(row.get("shard"))
    if shard is None:
        raise ClusterShapeError("shards_shard")
    prirep = _required_str(row.get("prirep"), "shards_prirep").lower()
    state = _required_str(row.get("state"), "shards_state").lower()
    return ShardInfo(
        index=index,
        shard=shard,
        role=_ROLE_BY_PRIREP.get(prirep, prirep),
        state=state,
        node=_shard_node(row.get("node"), state),
    )


def _read_node_name(row: Document) -> str:
    return _required_str(row.get("name"), "nodes_name")


def _required_str(value: object, reason: str) -> str:
    text = read_str(value)
    if text is None or text == "":
        raise ClusterShapeError(reason)
    return text


def _required_count(value: object, reason: str) -> int:
    """`cluster.health` の件数。JSON の整数で返る(`bool` と負の値は形の異常)。"""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ClusterShapeError(reason)
    return value


def _cat_int(value: object) -> int | None:
    """`cat.*` の整数の列は文字列で受ける。`^[0-9]+$` に一致すれば整数、それ以外(空・`null`・非数)は
    `None`。JSON の整数(非負)で返る場合も、同じ値として読む。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if not isinstance(value, str) or _DIGITS.fullmatch(value) is None:
        return None
    try:
        return int(value)
    except ValueError:
        # 桁数が Python の整数変換の上限を超える値。
        return None


def _lower_or_none(value: object) -> str | None:
    text = read_str(value)
    return text.lower() if text else None


def _shard_node(value: object, state: str) -> str | None:
    """未割り当て(空・`null`)は `None`。`relocating` は `移動元 -> IP ID 移動先` の形なので、
    移動元のノード名だけを使う(B 7.1)。
    """
    node = read_str(value)
    if not node:
        return None
    if state == _RELOCATING:
        node = node.partition(_RELOCATION_SEPARATOR)[0]
    return node or None


def _complete_indices(indices: Sequence[IndexInfo], shards: Sequence[ShardInfo]) -> list[IndexInfo]:
    """シャード一覧にあってインデックス一覧にないインデックスを、`status`・`document_count` が
    `None` で補う(インデックス一覧にあってシャード一覧にないものは、そのまま)。
    """
    known_names = {index.name for index in indices}
    missing_names = dict.fromkeys(shard.index for shard in shards if shard.index not in known_names)
    return [*indices, *(IndexInfo(name, None, None) for name in missing_names)]


def _index_order(index: IndexInfo) -> tuple[int, str]:
    rank = (
        _STATUS_RANK.get(index.status, _OTHER_STATUS_RANK) if index.status else _OTHER_STATUS_RANK
    )
    return (rank, index.name)


def _shard_order(shard: ShardInfo) -> tuple[str, int, int, str]:
    """インデックス名、シャード番号、primary を先、ノード名(`None` は先頭)の順。"""
    return (shard.index, shard.shard, 0 if shard.role == _PRIMARY else 1, shard.node or "")

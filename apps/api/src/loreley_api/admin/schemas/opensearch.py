"""EP-12 の DTO(B 7.1)。"""

from loreley_api.admin.schemas.common import ResponseModel


class ClusterSummary(ResponseModel):
    name: str
    status: str
    node_count: int
    active_shards: int
    relocating_shards: int
    initializing_shards: int
    unassigned_shards: int


class NodeEntry(ResponseModel):
    name: str


class IndexEntry(ResponseModel):
    name: str
    # `shards` にあって `indices` にないインデックスは `null`(補った行)。
    status: str | None
    # 取得できない(クローズ済みなど)は `null`。0 件と区別する。
    document_count: int | None


class ShardEntry(ResponseModel):
    index: str
    shard: int
    role: str
    state: str
    node: str | None


class ClusterResponse(ResponseModel):
    fetched_at: str
    cluster: ClusterSummary
    nodes: list[NodeEntry]
    indices: list[IndexEntry]
    shards: list[ShardEntry]
    truncated: bool
    total_indices: int

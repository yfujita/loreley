"""`cluster.health`・`cat.*` の正規化(C 3.4。EP-12)。"""

from typing import Any

import pytest

from loreley_api.admin.base.constants import CLUSTER_INDEX_LIMIT
from loreley_api.admin.derivation.cluster_view import (
    ClusterInfo,
    ClusterShapeError,
    ClusterView,
    IndexInfo,
    ShardInfo,
    normalize_cluster,
)
from tests.fakes.clock import DEFAULT_NOW as NOW

HEALTH: dict[str, Any] = {
    "cluster_name": "loreley",
    "status": "yellow",
    "number_of_nodes": 1,
    "active_shards": 1,
    "relocating_shards": 0,
    "initializing_shards": 0,
    "unassigned_shards": 1,
}


def index_row(name: str, health: Any = "green", docs: Any = "0") -> dict[str, Any]:
    return {"index": name, "health": health, "docs.count": docs}


def shard_row(
    index: str, shard: Any = "0", prirep: str = "p", state: str = "STARTED", node: Any = "node-1"
) -> dict[str, Any]:
    return {"index": index, "shard": shard, "prirep": prirep, "state": state, "node": node}


def normalize(
    *,
    health: dict[str, Any] | None = None,
    indices: list[dict[str, Any]] | None = None,
    shards: list[dict[str, Any]] | None = None,
    nodes: list[dict[str, Any]] | None = None,
) -> ClusterView:
    return normalize_cluster(
        health if health is not None else HEALTH,
        indices or [],
        shards or [],
        nodes if nodes is not None else [{"name": "node-1"}],
        now=NOW,
    )


def test_the_example_of_the_spec_is_normalized() -> None:
    view = normalize(
        indices=[index_row("loreley-documents-000001", "yellow", "12846")],
        shards=[
            shard_row("loreley-documents-000001", "0", "p", "STARTED", "node-1"),
            shard_row("loreley-documents-000001", "0", "r", "UNASSIGNED", None),
        ],
    )

    assert view == ClusterView(
        fetched_at="2026-11-24T00:00:00.000Z",
        cluster=ClusterInfo("loreley", "yellow", 1, 1, 0, 0, 1),
        nodes=("node-1",),
        indices=(IndexInfo("loreley-documents-000001", "yellow", 12846),),
        shards=(
            ShardInfo("loreley-documents-000001", 0, "primary", "started", "node-1"),
            ShardInfo("loreley-documents-000001", 0, "replica", "unassigned", None),
        ),
        truncated=False,
        total_indices=1,
    )


def test_the_health_status_is_lowercased() -> None:
    assert normalize(health={**HEALTH, "status": "GREEN"}).cluster.status == "green"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12", 12),
        ("0", 0),
        ("007", 7),
        (7, 7),
        ("", None),
        (None, None),
        ("abc", None),
        ("-1", None),
        (-7, None),
        ("1.5", None),
        (" 1", None),
        # 全角数字は `^[0-9]+$` に一致しない。
        ("\uff11\uff12", None),
        # 桁数が Python の整数変換の上限を超える値。
        ("9" * 5_000, None),
    ],
    ids=lambda value: repr(value)[:20],
)
def test_a_cat_integer_column_is_read_from_digits_only(raw: Any, expected: int | None) -> None:
    view = normalize(indices=[index_row("a", docs=raw)])

    assert view.indices[0].document_count == expected


def test_a_closed_index_with_no_document_count_is_null_not_zero() -> None:
    view = normalize(indices=[index_row("closed", health=None, docs=None), index_row("empty")])

    assert {i.name: i.document_count for i in view.indices} == {"closed": None, "empty": 0}


@pytest.mark.parametrize(
    ("raw", "expected"), [("p", "primary"), ("r", "replica"), ("P", "primary"), ("x", "x")]
)
def test_prirep_is_expanded_and_an_unknown_value_is_passed_through_in_lower_case(
    raw: str, expected: str
) -> None:
    view = normalize(shards=[shard_row("a", prirep=raw)], indices=[index_row("a")])

    assert view.shards[0].role == expected


def test_a_shard_state_is_lowercased_and_an_unknown_state_is_passed_through() -> None:
    view = normalize(
        indices=[index_row("a")],
        shards=[shard_row("a", state="STARTED"), shard_row("a", "1", state="Weird")],
    )

    assert [s.state for s in view.shards] == ["started", "weird"]


@pytest.mark.parametrize(
    ("state", "node", "expected"),
    [
        ("RELOCATING", "node-1 -> 10.0.0.2 abc node-2", "node-1"),
        ("RELOCATING", "node-1", "node-1"),
        # 移動元だけを使う分解は、`relocating` のときだけ。
        ("STARTED", "node-1 -> x", "node-1 -> x"),
        ("UNASSIGNED", None, None),
        ("UNASSIGNED", "", None),
        ("RELOCATING", " -> node-2", None),
    ],
)
def test_the_node_of_a_shard(state: str, node: Any, expected: str | None) -> None:
    view = normalize(indices=[index_row("a")], shards=[shard_row("a", state=state, node=node)])

    assert view.shards[0].node == expected


def test_an_index_that_only_the_shards_know_is_completed_with_null_status_and_count() -> None:
    view = normalize(
        indices=[index_row("a")],
        shards=[shard_row("a"), shard_row("hidden")],
    )

    assert IndexInfo("hidden", None, None) in view.indices
    assert view.total_indices == 2


def test_an_index_without_shards_is_kept_as_it_is() -> None:
    view = normalize(indices=[index_row("a"), index_row("b")], shards=[shard_row("a")])

    assert [i.name for i in view.indices] == ["a", "b"]
    assert [s.index for s in view.shards] == ["a"]


def test_indices_are_ordered_by_health_then_name_with_unknown_last() -> None:
    view = normalize(
        indices=[
            index_row("z-green", "green"),
            index_row("b-yellow", "yellow"),
            index_row("a-red", "red"),
            index_row("a-none", None),
            index_row("a-green", "green"),
            index_row("c-weird", "purple"),
            index_row("a-yellow", "YELLOW"),
        ],
        shards=[shard_row("m-hidden")],
    )

    assert [i.name for i in view.indices] == [
        "a-red",
        "a-yellow",
        "b-yellow",
        "a-green",
        "z-green",
        "a-none",
        "c-weird",
        "m-hidden",
    ]


def test_names_are_ordered_by_code_point() -> None:
    view = normalize(indices=[index_row("b"), index_row("B"), index_row("a")])

    assert [i.name for i in view.indices] == ["B", "a", "b"]


def test_shards_are_ordered_by_index_number_primary_first_then_node() -> None:
    view = normalize(
        indices=[index_row("a"), index_row("b")],
        shards=[
            shard_row("b", "0", "p", node="n1"),
            shard_row("a", "10", "p", node="n1"),
            shard_row("a", "2", "r", node="n2"),
            shard_row("a", "2", "r", node="n1"),
            shard_row("a", "2", "p", node="n3"),
            shard_row("a", "2", "r", state="UNASSIGNED", node=None),
        ],
    )

    assert [(s.index, s.shard, s.role, s.node) for s in view.shards] == [
        ("a", 2, "primary", "n3"),
        ("a", 2, "replica", None),
        ("a", 2, "replica", "n1"),
        ("a", 2, "replica", "n2"),
        ("a", 10, "primary", "n1"),
        ("b", 0, "primary", "n1"),
    ]


def test_nodes_are_ordered_by_name() -> None:
    view = normalize(nodes=[{"name": "node-b"}, {"name": "node-a"}])

    assert view.nodes == ("node-a", "node-b")


def test_the_indices_are_not_truncated_at_the_limit_and_truncated_beyond_it() -> None:
    at_limit = normalize(indices=[index_row(f"i{n:05d}") for n in range(CLUSTER_INDEX_LIMIT)])
    over_limit = normalize(indices=[index_row(f"i{n:05d}") for n in range(CLUSTER_INDEX_LIMIT + 1)])

    assert (at_limit.truncated, len(at_limit.indices), at_limit.total_indices) == (
        False,
        CLUSTER_INDEX_LIMIT,
        CLUSTER_INDEX_LIMIT,
    )
    assert (over_limit.truncated, len(over_limit.indices), over_limit.total_indices) == (
        True,
        CLUSTER_INDEX_LIMIT,
        CLUSTER_INDEX_LIMIT + 1,
    )


def test_truncation_keeps_the_worst_indices_and_their_shards_only() -> None:
    healthy = [index_row(f"i{n:05d}", "green") for n in range(CLUSTER_INDEX_LIMIT)]
    view = normalize(
        indices=[*healthy, index_row("z-red", "red")],
        shards=[
            shard_row("z-red"),
            shard_row("i00000"),
            shard_row(f"i{CLUSTER_INDEX_LIMIT - 1:05d}"),
        ],
    )

    assert view.truncated is True
    assert view.total_indices == CLUSTER_INDEX_LIMIT + 1
    assert view.indices[0].name == "z-red"
    assert f"i{CLUSTER_INDEX_LIMIT - 1:05d}" not in {i.name for i in view.indices}
    # 切り詰めたインデックスのシャードは返さない。
    assert [s.index for s in view.shards] == ["i00000", "z-red"]


def test_the_total_counts_the_completed_indices_before_truncation() -> None:
    view = normalize(
        indices=[index_row(f"i{n:05d}") for n in range(CLUSTER_INDEX_LIMIT)],
        shards=[shard_row("only-in-shards")],
    )

    assert (view.truncated, view.total_indices) == (True, CLUSTER_INDEX_LIMIT + 1)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"cluster_name": None}, "health_cluster_name"),
        ({"cluster_name": ""}, "health_cluster_name"),
        ({"status": None}, "health_status"),
        ({"status": 1}, "health_status"),
        ({"number_of_nodes": "1"}, "health_number_of_nodes"),
        ({"active_shards": True}, "health_active_shards"),
        ({"relocating_shards": None}, "health_relocating_shards"),
        ({"initializing_shards": -1}, "health_initializing_shards"),
        ({"unassigned_shards": 1.5}, "health_unassigned_shards"),
    ],
)
def test_a_malformed_health_is_a_shape_error_with_a_fixed_reason(
    change: dict[str, Any], reason: str
) -> None:
    with pytest.raises(ClusterShapeError) as caught:
        normalize(health={**HEALTH, **change})

    assert caught.value.reason == reason


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"indices": [index_row("")]}, "indices_index"),
        ({"indices": [{"index": None, "health": "green", "docs.count": "1"}]}, "indices_index"),
        ({"shards": [shard_row("a", shard="x")]}, "shards_shard"),
        ({"shards": [shard_row("a", shard=None)]}, "shards_shard"),
        ({"shards": [shard_row("a", prirep="")]}, "shards_prirep"),
        ({"shards": [shard_row("a", state="")]}, "shards_state"),
        ({"shards": [shard_row("")]}, "shards_index"),
        ({"nodes": [{"name": None}]}, "nodes_name"),
    ],
)
def test_a_malformed_row_is_a_shape_error_with_a_fixed_reason(
    kwargs: dict[str, Any], reason: str
) -> None:
    with pytest.raises(ClusterShapeError) as caught:
        normalize(**kwargs)

    assert caught.value.reason == reason


def test_a_shape_error_does_not_carry_any_value() -> None:
    with pytest.raises(ClusterShapeError) as caught:
        normalize(health={**HEALTH, "cluster_name": 12345})

    assert "12345" not in str(caught.value)

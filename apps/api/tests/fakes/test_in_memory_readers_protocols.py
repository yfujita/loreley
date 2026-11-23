"""`InMemoryReaders` の各 Reader が、本物の Protocol のメソッドをすべて同じ形で持つこと。

型検査を使わないので、Protocol に足したメソッドを偽物に足し忘れると、偽物を使うテストが
`AttributeError` になる。ここで、足し忘れと引数・同期/非同期の食い違いを 1 か所で知らせる(D 7.2)。

Python 3.12 前提: 検査の補助(`protocol_conformance.py`)が、非公開の `inspect._ParameterKind`・
`_is_protocol` に依存する。Python を上げるときは `typing.is_protocol` などへ移行する。
"""

import re
from typing import Any

import pytest

from loreley_api.infrastructure.opensearch import ports
from tests.fakes.behavior import FakeBehavior
from tests.fakes.in_memory_readers import OPERATIONS, InMemoryReaders
from tests.fakes.protocol_conformance import (
    assert_same_methods_as_protocol,
    protocols_defined_in,
    public_methods,
)

PROTOCOLS: dict[str, type] = {
    "sources": ports.SourcesReader,
    "jobs": ports.JobsReader,
    "deletions": ports.DeletionsReader,
    "search_index": ports.SearchIndexReader,
    "counts": ports.CountsReader,
    "cluster": ports.ClusterReader,
}


def reader_name_of(protocol: type) -> str:
    """`SearchIndexReader` → `search_index`(`InMemoryReaders` の属性名)。"""
    snake_case = re.sub(r"(?<!^)(?=[A-Z])", "_", protocol.__name__).lower()
    return snake_case.removesuffix("_reader")


def test_every_reader_protocol_of_the_ports_is_listed() -> None:
    """Protocol を足したのに `PROTOCOLS`(と `InMemoryReaders`)に足し忘れる、を防ぐ。"""
    discovered = {reader_name_of(member): member for member in protocols_defined_in(ports).values()}

    assert discovered == PROTOCOLS


@pytest.mark.parametrize("reader_name", PROTOCOLS)
def test_the_fake_reader_has_every_protocol_method_with_the_same_parameters(
    reader_name: str,
) -> None:
    fake: Any = getattr(InMemoryReaders(), reader_name)

    assert_same_methods_as_protocol(fake, PROTOCOLS[reader_name], label=reader_name)


def test_the_operation_names_of_the_fake_are_exactly_the_protocol_methods() -> None:
    expected = {
        f"{reader_name}.{method_name}"
        for reader_name, protocol in PROTOCOLS.items()
        for method_name in public_methods(protocol)
    }

    assert expected == OPERATIONS


@pytest.mark.parametrize("operation", ["jobs.get_lock", "locks.get_locks", "jobs"])
def test_an_unknown_operation_name_is_rejected_instead_of_silently_accepted(
    operation: str,
) -> None:
    behavior = InMemoryReaders().behavior

    with pytest.raises(ValueError, match="unknown operation"):
        behavior.inject(operation, None)
    with pytest.raises(ValueError, match="unknown operation"):
        behavior.before(operation, lambda: None)
    with pytest.raises(ValueError, match="unknown operation"):
        behavior.calls_of(operation)


def test_a_behavior_without_known_operations_accepts_any_name() -> None:
    """`FakeBehavior` は Crawler・OpenSearch の偽物とも共有する(操作名の一覧は偽物ごとに持つ)。"""
    behavior = FakeBehavior()

    behavior.inject("anything", None)

    assert behavior.calls_of("anything") == []

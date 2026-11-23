"""`InMemoryReaders` の各 Reader が、本物の Protocol のメソッドをすべて同じ引数で持つこと。

型検査を使わないので、Protocol に足したメソッドを偽物に足し忘れると、偽物を使うテストが
`AttributeError` になる。ここで、足し忘れと引数の食い違いを 1 か所で知らせる(D 7.2)。
"""

import inspect
from typing import Any

import pytest

from loreley_api.infrastructure.opensearch import ports
from tests.fakes.in_memory_readers import InMemoryReaders

PROTOCOLS: dict[str, type] = {
    "sources": ports.SourcesReader,
    "jobs": ports.JobsReader,
    "deletions": ports.DeletionsReader,
    "search_index": ports.SearchIndexReader,
    "counts": ports.CountsReader,
    "cluster": ports.ClusterReader,
}


def public_methods(protocol: type) -> dict[str, inspect.Signature]:
    return {
        name: inspect.signature(method)
        for name, method in inspect.getmembers(protocol, inspect.isfunction)
        if not name.startswith("_")
    }


@pytest.mark.parametrize("reader_name", PROTOCOLS)
def test_the_fake_reader_has_every_protocol_method_with_the_same_parameters(
    reader_name: str,
) -> None:
    fake: Any = getattr(InMemoryReaders(), reader_name)

    for name, protocol_signature in public_methods(PROTOCOLS[reader_name]).items():
        assert hasattr(fake, name), f"{reader_name}.{name} is missing in the fake"
        fake_signature = inspect.signature(getattr(fake, name))
        protocol_parameters = [p for p in protocol_signature.parameters if p != "self"]
        assert list(fake_signature.parameters) == protocol_parameters, f"{reader_name}.{name}"

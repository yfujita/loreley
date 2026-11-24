"""プローブの偽物・本物が、Protocol と同じ形であること。

`test_fake_crawler_client_protocol.py` と同じ流儀(Protocol を自動で列挙し、メソッド・引数・
同期/非同期・操作名の過不足を確かめる)。
"""

import pytest

from loreley_api.infrastructure.opensearch import (
    OpenSearchHealthProbe,
    ReadOnlyOpenSearch,
    health_probe,
)
from loreley_api.infrastructure.probes import (
    HttpHealthProbe,
    HttpProbeConfig,
    WebDistProbe,
    ports,
)
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.fakes.fake_probes import (
    OPERATIONS,
    FakeHttpHealthProbe,
    FakeOpenSearchHealthProbe,
    FakeWebDistProbe,
)
from tests.fakes.protocol_conformance import (
    assert_same_methods_as_protocol,
    protocols_defined_in,
    public_methods,
)


def test_the_probe_modules_define_exactly_these_protocols() -> None:
    """Protocol を足したのに、偽物の検査に足し忘れる、を防ぐ。"""
    assert set(protocols_defined_in(ports)) == {"HttpHealthCheck", "WebDistCheck"}
    assert set(protocols_defined_in(health_probe)) == {"OpenSearchHealthCheck"}


@pytest.mark.parametrize(
    ("candidate", "protocol"),
    [
        (FakeHttpHealthProbe(), ports.HttpHealthCheck),
        (FakeWebDistProbe(), ports.WebDistCheck),
        (FakeOpenSearchHealthProbe(), health_probe.OpenSearchHealthCheck),
        (HttpHealthProbe(HttpProbeConfig(timeout_seconds=1.0)), ports.HttpHealthCheck),
        (WebDistProbe(), ports.WebDistCheck),
        (
            OpenSearchHealthProbe(ReadOnlyOpenSearch(FakeOpenSearchClient())),
            health_probe.OpenSearchHealthCheck,
        ),
    ],
    ids=["fake-http", "fake-web", "fake-opensearch", "http", "web", "opensearch"],
)
def test_each_probe_has_every_protocol_method_with_the_same_parameters(
    candidate: object, protocol: type
) -> None:
    assert_same_methods_as_protocol(candidate, protocol, label=type(candidate).__name__)


@pytest.mark.parametrize("protocol", [ports.HttpHealthCheck, ports.WebDistCheck])
def test_the_operation_names_of_the_fakes_are_exactly_the_protocol_methods(
    protocol: type,
) -> None:
    assert set(public_methods(protocol)) == OPERATIONS


@pytest.mark.parametrize("operation", ["check_url", "probe", "checks"])
def test_an_unknown_operation_name_is_rejected_instead_of_silently_accepted(
    operation: str,
) -> None:
    behavior = FakeHttpHealthProbe().behavior

    with pytest.raises(ValueError, match="unknown operation"):
        behavior.inject(operation, None)
    with pytest.raises(ValueError, match="unknown operation"):
        behavior.before(operation, lambda: None)
    with pytest.raises(ValueError, match="unknown operation"):
        behavior.calls_of(operation)

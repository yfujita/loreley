"""レジストリと保護ラッパ(module 4.10。CM-P-7)。"""

from pathlib import Path

import pytest

from loreley_crawler.connectors.filesystem import FileSystemConnector, FileSystemSettings
from loreley_crawler.connectors.interface import (
    ConnectorError,
    ErrorCategory,
    ErrorScope,
    RetryHint,
)
from loreley_crawler.connectors.registry import (
    FILE_SYSTEM,
    ConnectorRegistry,
    create_connector_registry,
)
from tests.fakes.fake_connector import CREATE, VALIDATE_CONFIG, FakeConnector, FakeConnectorType
from tests.fakes.fake_fs_ops import ScriptedFsOps


def test_only_file_system_is_registered_in_the_mvp() -> None:
    registry = create_connector_registry()

    assert FILE_SYSTEM == "file_system"
    assert registry.registered_names == {"file_system"}
    assert registry.find("web") is None
    assert registry.find("") is None
    assert registry.find("FILE_SYSTEM") is None


def test_the_file_system_type_validates_and_creates_through_the_registry(tmp_path: Path) -> None:
    connector_type = create_connector_registry().find("file_system")
    assert connector_type is not None

    connector_type.validate_config({"root": str(tmp_path)})
    connector = connector_type.create("src", {"root": str(tmp_path)})

    assert isinstance(connector, FileSystemConnector)


def test_fs_ops_and_settings_reach_the_file_system_type(tmp_path: Path) -> None:
    fs = ScriptedFsOps()
    registry = create_connector_registry(fs_ops=fs, fs_settings=FileSystemSettings(max_patterns=1))
    connector_type = registry.find("file_system")
    assert connector_type is not None

    connector_type.create("src", {"root": str(tmp_path)})
    with pytest.raises(ConnectorError) as exc_info:
        connector_type.validate_config({"root": "/x", "include_patterns": ["a", "b"]})

    assert fs.behavior.calls  # 注入した FsOps が使われた
    assert exc_info.value.category is ErrorCategory.CONFIG_INVALID


def test_a_connector_error_passes_through_the_guard_unchanged() -> None:
    inner = FakeConnectorType()
    error = ConnectorError.of(ErrorCategory.CONFIG_INVALID, "bad")
    inner.behavior.inject(VALIDATE_CONFIG, error)
    inner.behavior.inject(CREATE, error)
    guarded = ConnectorRegistry({"fake": inner}).find("fake")
    assert guarded is not None

    for call in (lambda: guarded.validate_config({}), lambda: guarded.create("src", {})):
        with pytest.raises(ConnectorError) as exc_info:
            call()
        assert exc_info.value.category is ErrorCategory.CONFIG_INVALID
        assert exc_info.value.message == "bad"


@pytest.mark.parametrize("operation", [VALIDATE_CONFIG, CREATE])
def test_an_unexpected_exception_becomes_an_internal_error_of_scope_source(
    operation: str,
) -> None:
    inner = FakeConnectorType()
    inner.behavior.inject(operation, KeyError("SECRET-CONFIG-VALUE"))
    guarded = ConnectorRegistry({"fake": inner}).find("fake")
    assert guarded is not None

    with pytest.raises(ConnectorError) as exc_info:
        if operation == VALIDATE_CONFIG:
            guarded.validate_config({})
        else:
            guarded.create("src", {})

    error = exc_info.value
    assert error.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert (error.scope, error.retry) == (ErrorScope.SOURCE, RetryHint.UNKNOWN)
    assert "SECRET" not in error.message


def test_the_guard_passes_the_arguments_and_the_connector_through() -> None:
    connector = FakeConnector()
    inner = FakeConnectorType(connector)
    guarded = ConnectorRegistry({"fake": inner}).find("fake")
    assert guarded is not None
    config = {"any": "thing"}

    guarded.validate_config(config)
    created = guarded.create("src-1", config)

    assert created is connector
    assert inner.validated_configs == [config]
    assert inner.created == [("src-1", config)]


def test_the_registry_returns_the_same_guarded_type_for_the_same_name() -> None:
    registry = create_connector_registry()

    assert registry.find("file_system") is registry.find("file_system")

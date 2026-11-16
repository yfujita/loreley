"""`connector_type` から保護済みの `ConnectorType` を引くレジストリ(module 4.10。CM-P-7)。

MVP の `connector_type` は `file_system` だけ。レジストリが返す `ConnectorType` は保護ラッパで、
`validate_config`・`create` で `ConnectorError` 以外の例外が出たら `connector_internal_error`
(source)に変換する。論理上の共通処理(interface 3.2)の一部を、`sources`・`crawl` が `documents`
に依存せずに受けられるようここに置く(R3)。列挙・取得の変換は `documents` が行う。
"""

from collections.abc import Mapping

from loreley_crawler.connectors.filesystem import FileSystemConnectorType, FileSystemSettings, FsOps
from loreley_crawler.connectors.interface import (
    Connector,
    ConnectorType,
    ErrorScope,
    converting_unexpected_errors,
)

FILE_SYSTEM = "file_system"


class _GuardedConnectorType(ConnectorType):
    def __init__(self, inner: ConnectorType) -> None:
        self._inner = inner

    def validate_config(self, connector_config: object) -> None:
        with converting_unexpected_errors(ErrorScope.SOURCE):
            self._inner.validate_config(connector_config)

    def create(self, source_id: str, connector_config: object) -> Connector:
        with converting_unexpected_errors(ErrorScope.SOURCE):
            return self._inner.create(source_id, connector_config)


class ConnectorRegistry:
    def __init__(self, connector_types: Mapping[str, ConnectorType]) -> None:
        self._connector_types = {
            name: _GuardedConnectorType(connector_type)
            for name, connector_type in connector_types.items()
        }

    @property
    def registered_names(self) -> frozenset[str]:
        return frozenset(self._connector_types)

    def find(self, connector_type: str) -> ConnectorType | None:
        """登録されていなければ None(`sources` が `connector_type` の検証に使う)。"""
        return self._connector_types.get(connector_type)


def create_connector_registry(
    *, fs_ops: FsOps | None = None, fs_settings: FileSystemSettings | None = None
) -> ConnectorRegistry:
    """MVP のレジストリ(`file_system` だけ)。`main.py` が組み立てる。"""
    return ConnectorRegistry({FILE_SYSTEM: FileSystemConnectorType(fs_ops, fs_settings)})

"""FileSystem の `ConnectorType` と `Connector`(FS 設計書 1.3・3.2・9.1)。"""

import codecs

from loreley_crawler.connectors.filesystem.config import FileSystemConfig, parse_config
from loreley_crawler.connectors.filesystem.enumeration import FileSystemEnumerationStream
from loreley_crawler.connectors.filesystem.errors import describe_path, translating_root_errors
from loreley_crawler.connectors.filesystem.fetch import fetch_document
from loreley_crawler.connectors.filesystem.fs_ops import FsOps, OsFsOps
from loreley_crawler.connectors.filesystem.settings import FileSystemSettings
from loreley_crawler.connectors.interface import (
    Connector,
    ConnectorError,
    ConnectorType,
    DocumentRef,
    EnumerationStream,
    ErrorCategory,
    ErrorScope,
    FetchedDocument,
)


class FileSystemConnector(Connector):
    """保持する資源がないので、`close` は何もしない。列挙の打ち切りは `EnumerationStream.close`。"""

    def __init__(
        self,
        *,
        source_id: str,
        config: FileSystemConfig,
        fs: FsOps,
        settings: FileSystemSettings,
        root_real: str | None,
    ) -> None:
        self._source_id = source_id
        self._config = config
        self._fs = fs
        self._settings = settings
        self._root_real = root_real

    def enumerate(self) -> EnumerationStream:
        return FileSystemEnumerationStream(
            source_id=self._source_id,
            config=self._config,
            fs=self._fs,
            root_real=self._root_real,
            path_max_chars=self._settings.message_path_max_chars,
        )

    def fetch(self, ref: DocumentRef, max_bytes: int) -> FetchedDocument:
        return fetch_document(self._fs, self._config, self._settings, ref, max_bytes)

    def close(self) -> None:
        pass


class FileSystemConnectorType(ConnectorType):
    """`fs_ops` は OS 呼び出しの窓口(既定は `os`。テストは偽の `FsOps` を渡す。module CM-P-9)。"""

    def __init__(
        self, fs_ops: FsOps | None = None, settings: FileSystemSettings | None = None
    ) -> None:
        self._fs = fs_ops if fs_ops is not None else OsFsOps()
        self._settings = settings if settings is not None else FileSystemSettings()

    def validate_config(self, connector_config: object) -> None:
        parse_config(connector_config, self._settings)

    def create(self, source_id: str, connector_config: object) -> Connector:
        """ルートを確認する(3.2)。失敗は、開始通知の前にジョブを `failed` にする根拠になる。"""
        config = parse_config(connector_config, self._settings)
        self._check_filesystem_encoding()
        max_chars = self._settings.message_path_max_chars

        with translating_root_errors(config.root, max_chars=max_chars):
            root_stat = self._fs.stat(config.root)
            if not root_stat.is_directory:
                raise ConnectorError.of(
                    ErrorCategory.SOURCE_NOT_FOUND,
                    describe_path("ルートがディレクトリでない", config.root, max_chars=max_chars),
                )
            # 中身は読まない。権限・I/O の失敗をここで検出するため。
            with self._fs.scandir(config.root):
                pass
            root_real = self._fs.realpath(config.root) if config.follow_symlinks else None

        return FileSystemConnector(
            source_id=source_id,
            config=config,
            fs=self._fs,
            settings=self._settings,
            root_real=root_real,
        )

    def _check_filesystem_encoding(self) -> None:
        """名前を UTF-8 と `surrogateescape` で扱う前提(8.1。CFS-P-22)。

        崩れると、どのバイトが孤立サロゲートになるかが変わり、`external_id` が変わる。
        """
        encoding = self._fs.filesystem_encoding()
        try:
            is_utf8 = codecs.lookup(encoding).name == "utf-8"
        except LookupError:
            is_utf8 = False
        if not is_utf8:
            raise ConnectorError.of(
                ErrorCategory.CONNECTOR_INTERNAL_ERROR,
                f"ファイルシステムのエンコーディングが UTF-8 でない: {encoding}",
                scope=ErrorScope.SOURCE,
            )

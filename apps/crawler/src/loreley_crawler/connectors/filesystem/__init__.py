"""FileSystem Connector(MVP)。"""

from loreley_crawler.connectors.filesystem.connector import (
    FileSystemConnector,
    FileSystemConnectorType,
)
from loreley_crawler.connectors.filesystem.fs_ops import (
    DirEntryLike,
    FileStat,
    FsOps,
    OsFsOps,
)
from loreley_crawler.connectors.filesystem.settings import FileSystemSettings

__all__ = [
    "DirEntryLike",
    "FileStat",
    "FileSystemConnector",
    "FileSystemConnectorType",
    "FileSystemSettings",
    "FsOps",
    "OsFsOps",
]

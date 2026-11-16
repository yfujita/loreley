"""文書の取得(`fetch(ref, max_bytes)`。FS 設計書 5章・6章。案: CFS-P-13〜17)。

手順: `locator` の検査 → `open` → `fstat`(通常ファイルか。上限を超えていれば**読まずに** `oversize`)
→ `max_bytes + 1` バイトまで読む → もう一度 `fstat`(取得中の変更の検出)。
サイズの確認から読み取りまで同じ fd を使い、確認と読み取りの間の差し替えによる
食い違いを避ける。
"""

import os
import unicodedata
from datetime import UTC, datetime, timedelta

from loreley_crawler.connectors.filesystem.config import FileSystemConfig
from loreley_crawler.connectors.filesystem.errors import describe_path, translating_fetch_errors
from loreley_crawler.connectors.filesystem.fs_ops import FileStat, FsOps
from loreley_crawler.connectors.filesystem.paths import join_path
from loreley_crawler.connectors.filesystem.settings import FileSystemSettings
from loreley_crawler.connectors.interface import (
    ConnectorError,
    DocumentMetadata,
    DocumentRef,
    ErrorCategory,
    FetchedDocument,
)

# `mtime` の起点。日時として表せない `mtime` の代わりの固定値でもある(取得のたびに値が変わって、
# メタデータが毎回更新されるのを避ける。5.4)。
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_MIME_TYPES_BY_EXTENSION = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".html": "text/html",
    ".htm": "text/html",
    ".pdf": "application/pdf",
}
# 対応外の拡張子(包含パターンで追加したもの・拡張子なし)。拒否はしない(CI-P-16)。
FALLBACK_MIME_TYPE = "application/octet-stream"


def mime_type_of(file_name: str) -> str:
    return _MIME_TYPES_BY_EXTENSION.get(os.path.splitext(file_name)[1].lower(), FALLBACK_MIME_TYPE)


def modified_time_of(mtime_ns: int) -> datetime:
    """`mtime` を UTC の日時にする。マイクロ秒への変換は切り捨て(Indexer がミリ秒に正規化する)。"""
    try:
        return _EPOCH + timedelta(microseconds=mtime_ns // 1000)
    except (ValueError, OverflowError):
        return _EPOCH


def fetch_document(
    fs: FsOps,
    config: FileSystemConfig,
    settings: FileSystemSettings,
    ref: DocumentRef,
    max_bytes: int,
) -> FetchedDocument:
    if max_bytes < 0:
        raise ValueError("max_bytes must not be negative")
    if not isinstance(ref.locator, str):
        raise TypeError("locator of a file system document must be a string")
    relative_path = ref.locator
    max_chars = settings.message_path_max_chars
    if _escapes_root(relative_path):
        # 列挙が返した値は通らない道。`root` の外を読まないための防御。
        raise ConnectorError.of(
            ErrorCategory.FETCH_NOT_FOUND,
            describe_path("文書の場所が不正", relative_path, max_chars=max_chars),
        )

    with translating_fetch_errors(relative_path, max_chars=max_chars):
        fd = fs.open(join_path(config.root, relative_path), _open_flags(config))
        try:
            content, final_stat = _read_unchanged(fs, fd, relative_path, max_bytes, settings)
        finally:
            fs.close(fd)

    return FetchedDocument(content, _metadata_of(relative_path, final_stat))


def _escapes_root(relative_path: str) -> bool:
    return (
        relative_path.startswith("/") or "\0" in relative_path or ".." in relative_path.split("/")
    )


def _open_flags(config: FileSystemConfig) -> int:
    # O_NONBLOCK: 列挙の後で FIFO に差し替えられても、`open` が戻らなくなるのを防ぐ
    # (通常ファイルの読み取りには影響しない)。
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC
    if not config.follow_symlinks:
        flags |= os.O_NOFOLLOW  # 最後の構成要素がリンクなら ELOOP
    return flags


def _read_unchanged(
    fs: FsOps, fd: int, relative_path: str, max_bytes: int, settings: FileSystemSettings
) -> tuple[bytes, FileStat]:
    max_chars = settings.message_path_max_chars
    before = fs.fstat(fd)
    if not before.is_regular_file:
        # 列挙の後でディレクトリ・FIFO などに変わった。内容は読まない。
        raise ConnectorError.of(
            ErrorCategory.FETCH_NOT_FOUND,
            describe_path("通常ファイルでなくなった", relative_path, max_chars=max_chars),
        )
    if before.size > max_bytes:
        raise _oversize(relative_path, max_chars)

    content = _read_up_to(fs, fd, max_bytes + 1, settings.read_chunk_bytes)
    if len(content) > max_bytes:
        raise _oversize(relative_path, max_chars)  # 読み取り中に大きくなった

    after = fs.fstat(fd)
    changed = (after.size, after.mtime_ns) != (before.size, before.mtime_ns)
    if changed or len(content) != after.size:
        raise ConnectorError.of(
            ErrorCategory.FETCH_TRANSIENT,
            describe_path("取得中に文書が変更された", relative_path, max_chars=max_chars),
        )
    return content, after


def _read_up_to(fs: FsOps, fd: int, limit: int, chunk_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total < limit:
        chunk = fs.read(fd, min(chunk_bytes, limit - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _oversize(relative_path: str, max_chars: int) -> ConnectorError:
    return ConnectorError.of(
        ErrorCategory.OVERSIZE,
        describe_path("原本が上限を超えている", relative_path, max_chars=max_chars),
    )


def _metadata_of(relative_path: str, final_stat: FileStat) -> DocumentMetadata:
    file_name = relative_path.rsplit("/", 1)[-1]
    # `title`・`path` は NFC にする。Indexer は `external_id` と本文だけを NFC にするので、
    # macOS 由来の NFD の名前がそのまま検索・表示に出るのを避ける(5.3)。孤立サロゲートは
    # 変えない(共通処理が表示用に置換する)。
    return DocumentMetadata(
        title=unicodedata.normalize("NFC", file_name),
        mime_type=mime_type_of(file_name),
        source_updated_at=modified_time_of(final_stat.mtime_ns),
        path=unicodedata.normalize("NFC", relative_path),
        url=None,
    )

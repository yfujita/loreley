"""ディレクトリの再帰走査による列挙(FS 設計書 4章・9.1。案: CFS-P-5〜8・12)。

`os.walk`・`glob`・`pathlib` の `rglob` は使わない(`OSError` を握りつぶし、権限のない
ディレクトリを黙って飛ばすため。I-30)。`FsOps.scandir` を直接使い、読めなかったときは列挙を
`enumeration_incomplete` で失敗させる(完全でない列挙を `Completed` にしない。interface 3.3 の 2)。

メモリに載るのは処理中の 1 ディレクトリのエントリ一覧と、未走査のディレクトリのスタックだけで、
文書の全件は持たない(interface 3.3 の 6)。返す順序は規定しない。
"""

import logging
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum, auto

from loreley_crawler.connectors.filesystem.config import FileSystemConfig, has_default_extension
from loreley_crawler.connectors.filesystem.errors import (
    BROKEN_LINK_ERRNOS,
    enumeration_incomplete,
    translating_root_errors,
)
from loreley_crawler.connectors.filesystem.fs_ops import DirEntryLike, FsOps
from loreley_crawler.connectors.filesystem.paths import is_inside
from loreley_crawler.connectors.filesystem.patterns import matches_any
from loreley_crawler.connectors.interface import Completed, DocumentRef, EnumerationStream

logger = logging.getLogger(__name__)

DeviceAndInode = tuple[int, int]


class _EntryKind(Enum):
    FILE = auto()
    DIRECTORY = auto()


@dataclass(frozen=True)
class _PendingDirectory:
    path: str
    relative_prefix: str  # 空、または `/` で終わる相対パス
    is_root: bool
    # 経路上のディレクトリの (st_dev, st_ino)。`follow_symlinks=true` のときだけ持つ(4.2)。
    ancestors: tuple[DeviceAndInode, ...]


@dataclass
class EnumerationSummary:
    """列挙の終了時にログへ出す件数(9.4)。ファイル名は持たない。"""

    directories_scanned: int = 0
    documents_returned: int = 0
    ignored_hidden: int = 0
    ignored_symlink: int = 0
    ignored_other_kind: int = 0
    ignored_excluded: int = 0
    ignored_not_included: int = 0
    ignored_broken_symlink: int = 0
    ignored_outside_root: int = 0
    ignored_ancestor_loop: int = 0


@dataclass
class _Walker:
    """`FileSystemEnumerationStream` の走査の本体。"""

    source_id: str
    config: FileSystemConfig
    fs: FsOps
    root_real: str | None  # `follow_symlinks=true` のときだけ
    path_max_chars: int
    summary: EnumerationSummary = field(default_factory=EnumerationSummary)

    def walk(self) -> Iterator[DocumentRef]:
        stack = [self._root_directory()]
        while stack:
            directory = stack.pop()
            entries = self._read_directory(directory)
            self.summary.directories_scanned += 1
            for entry in entries:
                found = self._examine(entry, directory)
                if isinstance(found, DocumentRef):
                    self.summary.documents_returned += 1
                    yield found
                elif found is not None:
                    stack.append(found)

    def _root_directory(self) -> _PendingDirectory:
        ancestors: tuple[DeviceAndInode, ...] = ()
        if self.config.follow_symlinks:
            with translating_root_errors(self.config.root, max_chars=self.path_max_chars):
                ancestors = (self._device_and_inode(self.config.root),)
        return _PendingDirectory(self.config.root, "", is_root=True, ancestors=ancestors)

    def _read_directory(self, directory: _PendingDirectory) -> list[DirEntryLike]:
        # 全件読み切って閉じる。深い木で、走査の経路の分だけ fd を開いたままにしない(9.2)。
        if directory.is_root:
            with translating_root_errors(self.config.root, max_chars=self.path_max_chars):
                return self._list(directory.path)
        try:
            return self._list(directory.path)
        except OSError as error:
            relative_path = directory.relative_prefix.removesuffix("/")
            raise enumeration_incomplete(
                error, relative_path, max_chars=self.path_max_chars
            ) from None

    def _list(self, path: str) -> list[DirEntryLike]:
        with self.fs.scandir(path) as iterator:
            return list(iterator)

    def _examine(
        self, entry: DirEntryLike, directory: _PendingDirectory
    ) -> DocumentRef | _PendingDirectory | None:
        """エントリを 4.1 の順に判定する。ループ内の `OSError` は列挙の失敗にする(4.4)。"""
        relative_path = directory.relative_prefix + entry.name
        try:
            return self._judge(entry, directory, relative_path)
        except OSError as error:
            raise enumeration_incomplete(
                error, relative_path, max_chars=self.path_max_chars
            ) from None

    def _judge(
        self, entry: DirEntryLike, directory: _PendingDirectory, relative_path: str
    ) -> DocumentRef | _PendingDirectory | None:
        if not self.config.include_hidden and entry.name.startswith("."):
            self.summary.ignored_hidden += 1
            return None
        kind = self._classify(entry)
        if kind is None:
            return None
        match_key = unicodedata.normalize("NFC", relative_path) if self.config.uses_patterns else ""
        if matches_any(self.config.exclude_patterns, match_key):
            # 除外に一致したディレクトリは開かず、配下も走査しない。
            self.summary.ignored_excluded += 1
            return None
        if kind is _EntryKind.DIRECTORY:
            return self._pending_directory(entry, directory, relative_path)
        included = has_default_extension(entry.name) or matches_any(
            self.config.include_patterns, match_key
        )
        if not included:
            self.summary.ignored_not_included += 1
            return None
        # `external_id` も `locator` も OS の名前を加工しない(NFC・置換は共通処理。8.1)。
        return DocumentRef(external_id=relative_path, locator=relative_path, size_hint=None)

    def _classify(self, entry: DirEntryLike) -> _EntryKind | None:
        """通常ファイルとディレクトリだけを対象にする。FIFO などは開くと戻らないので対象外。"""
        if not entry.is_symlink():
            if entry.is_dir(follow_symlinks=False):
                return _EntryKind.DIRECTORY
            if entry.is_file(follow_symlinks=False):
                return _EntryKind.FILE
            # FIFO・ソケット・デバイスと、判定の前に消えたエントリ。
            self.summary.ignored_other_kind += 1
            return None
        if not self.config.follow_symlinks:
            self.summary.ignored_symlink += 1
            return None
        return self._classify_symlink(entry)

    def _classify_symlink(self, entry: DirEntryLike) -> _EntryKind | None:
        assert self.root_real is not None  # follow_symlinks=true の `create` が求める
        try:
            if not is_inside(self.root_real, self.fs.realpath(entry.path)):
                self.summary.ignored_outside_root += 1
                return None
            if entry.is_dir():
                return _EntryKind.DIRECTORY
            if entry.is_file():
                return _EntryKind.FILE
        except OSError as error:
            if error.errno not in BROKEN_LINK_ERRNOS:
                raise  # 先の親が通れない EACCES など。無視せず列挙の失敗にする。
        # 壊れたリンク(先がない・循環・先に至る途中が通常ファイル)と、通常でない種別の先。
        self.summary.ignored_broken_symlink += 1
        return None

    def _pending_directory(
        self, entry: DirEntryLike, directory: _PendingDirectory, relative_path: str
    ) -> _PendingDirectory | None:
        ancestors: tuple[DeviceAndInode, ...] = ()
        if self.config.follow_symlinks:
            device_and_inode = self._device_and_inode(entry.path)
            # 祖先へのループは、リンクで入るディレクトリだけが起こす。
            if entry.is_symlink() and device_and_inode in directory.ancestors:
                self.summary.ignored_ancestor_loop += 1
                return None
            ancestors = (*directory.ancestors, device_and_inode)
        return _PendingDirectory(
            path=entry.path,
            relative_prefix=f"{relative_path}/",
            is_root=False,
            ancestors=ancestors,
        )

    def _device_and_inode(self, path: str) -> DeviceAndInode:
        file_stat = self.fs.stat(path)
        return (file_stat.device, file_stat.inode)


class FileSystemEnumerationStream(EnumerationStream):
    """`next()` は 1 件ずつ返し、最後に `Completed` を返すか、`ConnectorError` を送出する。

    失敗(例外)の後の `next()` は、同じ例外を再送出する。ジェネレータは例外で終わると
    次の呼び出しで終わり扱いになるので、そのまま `Completed` を返さないための状態を持つ。
    """

    def __init__(
        self,
        *,
        source_id: str,
        config: FileSystemConfig,
        fs: FsOps,
        root_real: str | None,
        path_max_chars: int,
    ) -> None:
        self._walker = _Walker(source_id, config, fs, root_real, path_max_chars)
        self._documents = self._walker.walk()
        self._terminal: Completed | BaseException | None = None
        self._closed = False

    def next(self) -> DocumentRef | Completed:
        if self._closed:
            raise RuntimeError("enumeration stream is closed")
        if isinstance(self._terminal, BaseException):
            raise self._terminal
        if self._terminal is not None:
            return self._terminal
        try:
            document = next(self._documents, None)
        except BaseException as error:
            self._terminal = error
            raise
        if document is not None:
            return document
        self._terminal = Completed()
        self._log_summary()
        return self._terminal

    def close(self) -> None:
        # 走査を打ち切る。未走査のディレクトリのスタックはジェネレータごと捨てる。
        # 列挙は `Completed` にも失敗にもならず、未完了のまま終わる(interface 3.3 の 1)。
        self._closed = True
        self._documents.close()

    def _log_summary(self) -> None:
        summary = self._walker.summary
        logger.info(
            "file system enumeration completed: source_id=%s directories=%d documents=%d "
            "ignored(hidden=%d symlink=%d other_kind=%d excluded=%d not_included=%d "
            "broken_symlink=%d outside_root=%d ancestor_loop=%d)",
            self._walker.source_id,
            summary.directories_scanned,
            summary.documents_returned,
            summary.ignored_hidden,
            summary.ignored_symlink,
            summary.ignored_other_kind,
            summary.ignored_excluded,
            summary.ignored_not_included,
            summary.ignored_broken_symlink,
            summary.ignored_outside_root,
            summary.ignored_ancestor_loop,
        )

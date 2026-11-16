"""OS のファイルシステム呼び出しの窓口(`FsOps`。module CM-P-9)。

FS Connector は OS を直接呼ばず、すべてここを通す。テストは、呼び出しの時点を制御できる偽の
`FsOps` を `FileSystemConnectorType` の生成時に渡す(列挙・取得の途中でファイルが消える・
変わる状況を、決定的に再現するため。FS 設計書 9.2・10章 #13・#15・#17)。

読み取りの操作だけを持つ(書き込み・削除・属性変更をしない。CFS-K-2)。
"""

import os
import stat
import sys
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FileStat:
    """`stat`・`fstat` の結果のうち、FS Connector が使う項目だけ。"""

    mode: int
    size: int
    mtime_ns: int
    device: int
    inode: int

    @property
    def is_regular_file(self) -> bool:
        return stat.S_ISREG(self.mode)

    @property
    def is_directory(self) -> bool:
        return stat.S_ISDIR(self.mode)


class DirEntryLike(Protocol):
    """`os.DirEntry` のうち、走査が使う部分。

    `is_dir`・`is_file` は、エントリが存在しない(壊れたリンク・消えた)ときは例外にせず
    `False` を返し、リンクの循環などは `OSError` を送出する(`os.DirEntry` と同じ)。
    """

    @property
    def name(self) -> str: ...

    @property
    def path(self) -> str: ...

    def is_symlink(self) -> bool: ...

    def is_dir(self, *, follow_symlinks: bool = True) -> bool: ...

    def is_file(self, *, follow_symlinks: bool = True) -> bool: ...


class FsOps(ABC):
    """FS Connector が使う OS 呼び出し。失敗は `OSError` で表す(`os` と同じ)。"""

    @abstractmethod
    def scandir(self, path: str) -> AbstractContextManager[Iterator[DirEntryLike]]:
        """ディレクトリのエントリを走査する(`os.scandir`)。"""

    @abstractmethod
    def stat(self, path: str) -> FileStat:
        """シンボリックリンクをたどって状態を得る(`os.stat`)。"""

    @abstractmethod
    def realpath(self, path: str) -> str:
        """シンボリックリンクを解決した絶対パス(`os.path.realpath`。存在しなくても例外にしない)。"""

    @abstractmethod
    def open(self, path: str, flags: int) -> int:
        """ファイル記述子を返す(`os.open`)。"""

    @abstractmethod
    def fstat(self, fd: int) -> FileStat:
        """開いたファイルの状態を得る(`os.fstat`)。"""

    @abstractmethod
    def read(self, fd: int, num_bytes: int) -> bytes:
        """最大 `num_bytes` バイトを読む。ファイルの終わりでは空の `bytes`(`os.read`)。"""

    @abstractmethod
    def close(self, fd: int) -> None:
        """ファイル記述子を閉じる(`os.close`)。"""

    @abstractmethod
    def filesystem_encoding(self) -> str:
        """Python がファイル名の変換に使うエンコーディング(`sys.getfilesystemencoding`)。"""


class OsFsOps(FsOps):
    """`os` を呼ぶ既定の実装。"""

    def scandir(self, path: str) -> AbstractContextManager[Iterator[DirEntryLike]]:
        return os.scandir(path)

    def stat(self, path: str) -> FileStat:
        return _to_file_stat(os.stat(path))

    def realpath(self, path: str) -> str:
        return os.path.realpath(path)

    def open(self, path: str, flags: int) -> int:
        return os.open(path, flags)

    def fstat(self, fd: int) -> FileStat:
        return _to_file_stat(os.fstat(fd))

    def read(self, fd: int, num_bytes: int) -> bytes:
        return os.read(fd, num_bytes)

    def close(self, fd: int) -> None:
        os.close(fd)

    def filesystem_encoding(self) -> str:
        return sys.getfilesystemencoding()


def _to_file_stat(result: os.stat_result) -> FileStat:
    return FileStat(
        mode=result.st_mode,
        size=result.st_size,
        mtime_ns=result.st_mtime_ns,
        device=result.st_dev,
        inode=result.st_ino,
    )

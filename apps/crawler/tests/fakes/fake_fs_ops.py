"""`FsOps` の偽物(テスト用)。実ファイルシステム(一時ディレクトリ)の呼び出しに、
呼び出しの時点を制御する仕組みを足す。

`FakeBehavior`(フックと差し替え)を、操作ごとの「キー」(対象のパス)で使う。キーは、`FsOps` に
渡されるパスそのもの(`virtual_root` を使うときは仮想のパス)。FS 設計書 10章の #13・#15・#17 を
決定的に書くための注入点:

- `behavior.before(OPEN | READ | FSTAT | ..., callback, key=path)`: 次のその操作の直前に 1 回だけ
  `callback` を呼ぶ(読み取りの直前にファイルを変える、など)。同じ操作に複数登録すると、
  呼び出しごとに登録順に 1 つずつ使う(2 回目の `fstat` の直前、など)。
- `behavior.inject(op, outcome, key=path, times=...)`: その操作の代わりに `outcome` を返す、または
  例外なら送出する(`OSError(errno.EIO, ...)` で errno の分類を再現する、など)。
- 記録: `opened_flags`(`open` のフラグ)、`bytes_read`(`read` が実際に返した合計バイト数)、
  `open_scandir_count`・`max_open_scandir_count`(開いている `scandir` の現在数と最大同時数。
  読み切って閉じることの確認用)。
- エントリの判定(`IS_SYMLINK`・`IS_DIR`・`IS_FILE`)は、キーがエントリのパス。
  `inject(IS_DIR, False, key=path, times=None)` などで、判定の前に消えたエントリを再現する。

`virtual_root` を渡すと、`/` から始まるパスを、その実ディレクトリの下に読み替える
(ルートが `/` のときの挙動を、実際の `/` を走査せずに確かめるため)。
"""

import os
from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path

from loreley_crawler.connectors.filesystem import DirEntryLike, FileStat, FsOps, OsFsOps
from tests.fakes.behavior import FakeBehavior

SCANDIR = "scandir"
STAT = "stat"
REALPATH = "realpath"
OPEN = "open"
FSTAT = "fstat"
READ = "read"
CLOSE = "close"
FILESYSTEM_ENCODING = "filesystem_encoding"
IS_SYMLINK = "is_symlink"
IS_DIR = "is_dir"
IS_FILE = "is_file"


class ScriptedFsOps(FsOps):
    def __init__(self, inner: FsOps | None = None, *, virtual_root: Path | None = None) -> None:
        self._inner = inner if inner is not None else OsFsOps()
        self._base = None if virtual_root is None else os.path.realpath(virtual_root)
        self.behavior = FakeBehavior()
        self.opened_flags: list[int] = []
        self.bytes_read = 0
        self.open_scandir_count = 0
        self.max_open_scandir_count = 0
        self._paths_by_fd: dict[int, str] = {}

    def scandir(self, path: str) -> AbstractContextManager[Iterator[DirEntryLike]]:
        return _ScriptedScandir(self, path)

    def stat(self, path: str) -> FileStat:
        outcome = self.behavior.enter(STAT, path)
        if outcome is not None:
            return outcome.value
        return self._inner.stat(self._real(path))

    def realpath(self, path: str) -> str:
        outcome = self.behavior.enter(REALPATH, path)
        if outcome is not None:
            return outcome.value
        return self._virtual(self._inner.realpath(self._real(path)))

    def open(self, path: str, flags: int) -> int:
        self.opened_flags.append(flags)
        outcome = self.behavior.enter(OPEN, path)
        fd = outcome.value if outcome is not None else self._inner.open(self._real(path), flags)
        self._paths_by_fd[fd] = path
        return fd

    def fstat(self, fd: int) -> FileStat:
        outcome = self.behavior.enter(FSTAT, self._paths_by_fd[fd])
        if outcome is not None:
            return outcome.value
        return self._inner.fstat(fd)

    def read(self, fd: int, num_bytes: int) -> bytes:
        outcome = self.behavior.enter(READ, self._paths_by_fd[fd])
        if outcome is not None:
            return outcome.value
        data = self._inner.read(fd, num_bytes)
        self.bytes_read += len(data)
        return data

    def close(self, fd: int) -> None:
        self.behavior.enter(CLOSE, self._paths_by_fd[fd])
        self._inner.close(fd)

    def filesystem_encoding(self) -> str:
        outcome = self.behavior.enter(FILESYSTEM_ENCODING)
        if outcome is not None:
            return outcome.value
        return self._inner.filesystem_encoding()

    def _real(self, path: str) -> str:
        if self._base is None:
            return path
        return self._base + path if path != "/" else self._base

    def _virtual(self, real_path: str) -> str:
        if self._base is None:
            return real_path
        if real_path == self._base:
            return "/"
        if real_path.startswith(self._base + "/"):
            return real_path[len(self._base) :]
        return real_path


class _ScriptedScandir:
    """`scandir` の結果。`__enter__` から `__exit__` までを「開いている」と数える。

    ジェネレータ形式の `contextmanager` は、`__exit__` を呼ばずに捨てても参照が尽きると
    終了処理が走って数が戻る。閉じ忘れを見逃さないよう、明示的な `__exit__` だけで戻す。
    """

    def __init__(self, fs: ScriptedFsOps, path: str) -> None:
        self._fs = fs
        self._path = path
        self._inner: AbstractContextManager[Iterator[DirEntryLike]] | None = None

    def __enter__(self) -> Iterator[DirEntryLike]:
        self._fs.behavior.enter(SCANDIR, self._path)
        self._inner = self._fs._inner.scandir(self._fs._real(self._path))
        entries = self._inner.__enter__()
        self._fs.open_scandir_count += 1
        self._fs.max_open_scandir_count = max(
            self._fs.max_open_scandir_count, self._fs.open_scandir_count
        )
        return iter([_ScriptedEntry(self._fs, entry, self._path) for entry in entries])

    def __exit__(self, *exc_info: object) -> None:
        assert self._inner is not None
        self._fs.open_scandir_count -= 1
        self._inner.__exit__(*exc_info)


class _ScriptedEntry:
    """`DirEntryLike`。判定の前に `FakeBehavior` を通す。`path` は(仮想の)パス。"""

    def __init__(self, fs: ScriptedFsOps, inner: DirEntryLike, directory: str) -> None:
        self._fs = fs
        self._inner = inner
        self.name = inner.name
        self.path = directory.rstrip("/") + "/" + inner.name

    def is_symlink(self) -> bool:
        outcome = self._fs.behavior.enter(IS_SYMLINK, self.path)
        return outcome.value if outcome is not None else self._inner.is_symlink()

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        outcome = self._fs.behavior.enter(IS_DIR, self.path)
        if outcome is not None:
            return outcome.value
        return self._inner.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, *, follow_symlinks: bool = True) -> bool:
        outcome = self._fs.behavior.enter(IS_FILE, self.path)
        if outcome is not None:
            return outcome.value
        return self._inner.is_file(follow_symlinks=follow_symlinks)

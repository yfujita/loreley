"""FS Connector のテストの共通部品。"""

import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from loreley_crawler.connectors.filesystem import (
    FileSystemConnectorType,
    FileSystemSettings,
    FsOps,
)
from loreley_crawler.connectors.interface import (
    Completed,
    Connector,
    ConnectorError,
    DocumentRef,
    EnumerationStream,
)

SOURCE_ID = "src-fs"

# 権限エラーのテスト(FS 設計書 10章 #4・#12・#16)は、root では権限が効かず成功してしまう。
skip_if_root = pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0,
    reason="root ignores file permissions, so permission errors cannot be reproduced",
)


# `1` のとき、作れない FS での skip を失敗にする。Linux のコンテナで実行するときに指定して、
# Linux 専用のテストが黙って skip されるのを防ぐ(README に書く)。それ以外は何も変わらない。
REQUIRE_LINUX_NAMES_ENV = "LORELEY_REQUIRE_LINUX_NAMES"


def skip_or_fail_when_names_cannot_be_created(reason: str) -> None:
    if os.environ.get(REQUIRE_LINUX_NAMES_ENV) == "1":
        pytest.fail(f"{reason} ({REQUIRE_LINUX_NAMES_ENV}=1 requires these names to be creatable)")
    pytest.skip(reason)


def create_names_or_skip(root: Path, names: list[bytes], *, what: str) -> None:
    """`names`(バイト列の名前)を `root` の直下に作る。作れない FS では skip する。

    環境変数 `LORELEY_REQUIRE_LINUX_NAMES=1` のときは、skip ではなく失敗にする。

    非 UTF-8 の名前、NFC と NFD の併存、大文字小文字だけが違う名前は、macOS(APFS)では
    作れない(FS 設計書 10章の実行環境の注意)。OS の名前でなく、実際に作れるかで判定する。
    併存できる名前は、作った後に全部が別のエントリとして残っていることも確かめる。
    """
    root_bytes = os.fsencode(root)
    try:
        for name in names:
            fd = os.open(root_bytes + b"/" + name, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            os.close(fd)
    except OSError as error:
        skip_or_fail_when_names_cannot_be_created(
            f"this file system cannot create {what}: {error.strerror}"
        )
    if sorted(os.listdir(root_bytes)) != sorted(names):
        skip_or_fail_when_names_cannot_be_created(
            f"this file system cannot keep {what} as separate entries"
        )


def skip_unless_listed(directory: Path, name: str) -> None:
    """`name` が、作った名前のまま一覧に出なければ skip する(名前を正規化する FS を除く)。"""
    if name not in os.listdir(directory):
        pytest.skip("this file system normalizes file names, so an NFD name cannot be created")


def create_connector(
    root: Path | str,
    fs: FsOps | None = None,
    *,
    settings: FileSystemSettings | None = None,
    **config: Any,
) -> Connector:
    return FileSystemConnectorType(fs, settings).create(SOURCE_ID, {"root": str(root), **config})


def write_file(root: Path, relative_path: str, content: bytes = b"content") -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def drain(stream: EnumerationStream) -> tuple[list[DocumentRef], Completed | ConnectorError]:
    """終端(`Completed` か列挙の失敗)まで `next()` を呼ぶ。"""
    refs: list[DocumentRef] = []
    while True:
        try:
            item = stream.next()
        except ConnectorError as error:
            return refs, error
        if isinstance(item, Completed):
            return refs, item
        refs.append(item)


def enumerate_ids(connector: Connector) -> set[str]:
    """列挙が `Completed` で終わることを確かめ、`external_id` の集合を返す(順序は規定しない)。"""
    refs, terminal = drain(connector.enumerate())
    assert terminal == Completed(), terminal
    ids = {ref.external_id for ref in refs}
    assert len(ids) == len(refs)  # `follow_symlinks=false` なら同じパスを 2 度返さない
    return ids


def enumeration_failure(connector: Connector) -> ConnectorError:
    refs, terminal = drain(connector.enumerate())
    assert isinstance(terminal, ConnectorError), (refs, terminal)
    return terminal


def run_with_deadline[T](action: Callable[[], T], *, seconds: float = 10.0) -> T:
    """戻らなくなる退行(FIFO を開いて待ち続けるなど)を、ハングでなく失敗にする。"""
    outcome: list[T] = []
    errors: list[BaseException] = []

    def target() -> None:
        try:
            outcome.append(action())
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds)
    assert not thread.is_alive(), "the call did not return"
    if errors:
        raise errors[0]
    return outcome[0]

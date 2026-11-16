"""読み取り専用(FS 設計書 10章 #23)。

FS Connector は、書き込み・削除・属性変更をしない(CFS-K-2)。ここで確かめるのは次の 3 つ。
(1) 実行時に `open` が読み取りのフラグだけを使うこと。(2) `FsOps` に書き込み系の操作がないこと。
(3) OS の呼び出しが `fs_ops.py` に集約され、他のファイルが `os` の関数などを呼ばないこと。
コンテナで `:ro` のマウントに書き込めないことは、運用の確認(単体テストの対象外)。
"""

import ast
import os
from pathlib import Path

from loreley_crawler.connectors.filesystem import FsOps
from tests.connectors.filesystem.support import create_connector, drain, write_file
from tests.fakes.fake_fs_ops import ScriptedFsOps

FILESYSTEM_PACKAGE = (
    Path(__file__).resolve().parents[3] / "src" / "loreley_crawler" / "connectors" / "filesystem"
)
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND | os.O_EXCL

# `os.path.splitext` は文字列の処理で、OS を呼ばない。
ALLOWED_CALLS_OUTSIDE_FS_OPS = {"os.path.splitext"}
FORBIDDEN_MODULES = {"shutil", "glob", "pathlib", "subprocess", "tempfile", "io"}


def dotted_name(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


def opened_flags_of_a_run(tmp_path: Path, *, follow_symlinks: bool) -> list[int]:
    write_file(tmp_path, "a.txt", b"a")
    write_file(tmp_path, "dir/b.md", b"b")
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs, follow_symlinks=follow_symlinks)

    refs, _ = drain(connector.enumerate())
    for ref in refs:
        connector.fetch(ref, 100)

    return fs.opened_flags


def test_every_open_uses_exactly_the_documented_read_only_flags(tmp_path: Path) -> None:
    flags_list = opened_flags_of_a_run(tmp_path, follow_symlinks=False)

    assert len(flags_list) == 2
    for flags in flags_list:
        assert flags & WRITE_FLAGS == 0
        # 読み取りのフラグと、FIFO に差し替えられても戻らなくならない `O_NONBLOCK` と、
        # リンクを開かない `O_NOFOLLOW`(リンクをたどらない設定のとき)だけ。
        assert flags == os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW


def test_following_links_drops_only_o_nofollow(tmp_path: Path) -> None:
    flags_list = opened_flags_of_a_run(tmp_path, follow_symlinks=True)

    assert len(flags_list) == 2
    for flags in flags_list:
        assert flags == os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC


def test_the_fs_ops_interface_has_only_read_operations() -> None:
    assert FsOps.__abstractmethods__ == {
        "scandir",
        "stat",
        "realpath",
        "open",
        "fstat",
        "read",
        "close",
        "filesystem_encoding",
    }


def test_the_files_must_not_touch_the_os_except_through_fs_ops() -> None:
    violations: list[str] = []
    for path in sorted(FILESYSTEM_PACKAGE.glob("*.py")):
        if path.name == "fs_ops.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = dotted_name(node.func)
                if (
                    name is not None
                    and name.startswith("os.")
                    and (name not in ALLOWED_CALLS_OUTSIDE_FS_OPS)
                ):
                    violations.append(f"{path.name}: {name}()")
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module.split(".")[0]]
            violations += [f"{path.name}: imports {m}" for m in modules if m in FORBIDDEN_MODULES]

    assert violations == []

"""パスの結合と、ルートの内外の判定(FS 設計書 4.2・9.1)。"""

import pytest

from loreley_crawler.connectors.filesystem.paths import is_inside, join_path


@pytest.mark.parametrize(
    ("base", "name", "expected"),
    [
        ("/mnt/docs", "a.md", "/mnt/docs/a.md"),
        ("/mnt/docs/", "a.md", "/mnt/docs/a.md"),
        ("/", "a.md", "/a.md"),  # `root` が `/` のとき `//a.md` にしない
        ("/", "dir/a.md", "/dir/a.md"),
    ],
)
def test_join_path(base: str, name: str, expected: str) -> None:
    assert join_path(base, name) == expected


@pytest.mark.parametrize(
    ("root_real", "real_path", "expected"),
    [
        ("/a/b", "/a/b", True),  # 等しい
        ("/a/b", "/a/b/c/d", True),  # 配下
        ("/a/b", "/a/bc", False),  # 名前が前方一致するだけの兄弟
        ("/a/b", "/a/b-other/x", False),
        ("/a/b", "/a", False),  # 親
        ("/a/b", "/x/y", False),
        ("/", "/", True),  # `root` が `/` なら、すべて内
        ("/", "/any/where", True),
    ],
)
def test_is_inside(root_real: str, real_path: str, expected: bool) -> None:
    assert is_inside(root_real, real_path) is expected

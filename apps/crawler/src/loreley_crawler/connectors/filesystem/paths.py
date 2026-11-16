"""パスの結合と、ルートの内外の判定(FS 設計書 4.2・9.1)。"""

import posixpath


def join_path(base: str, name: str) -> str:
    """`root` が `/` のときに `//name` にしない結合。"""
    return f"{base.rstrip('/')}/{name}"


def is_inside(root_real: str, real_path: str) -> bool:
    """`real_path` が `root_real` と等しいか、その配下か。`root_real` が `/` ならすべて内。"""
    return posixpath.commonpath([root_real, real_path]) == root_real

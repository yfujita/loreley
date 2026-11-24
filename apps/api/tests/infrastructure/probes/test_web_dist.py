"""`WebDistProbe`: `index.html` が読めるか(C 6.3。C 11章 10)。毎回確認する(キャッシュしない)。"""

import os
from pathlib import Path

import pytest

from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.infrastructure.probes import WebDistProbe

NORMAL = ProbeOutcome("normal", None)
MISSING = ProbeOutcome("abnormal", "missing")


def test_a_readable_index_html_is_normal(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")

    assert WebDistProbe().check(str(tmp_path)) == NORMAL


def test_a_one_byte_index_html_is_normal(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_bytes(b"x")

    assert WebDistProbe().check(str(tmp_path)) == NORMAL


def test_a_missing_directory_is_abnormal_missing(tmp_path: Path) -> None:
    assert WebDistProbe().check(str(tmp_path / "no-such-directory")) == MISSING


def test_a_directory_without_index_html_is_abnormal_missing(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "other.html").write_text("x", encoding="utf-8")

    assert WebDistProbe().check(str(tmp_path)) == MISSING


def test_an_empty_index_html_is_abnormal_missing(tmp_path: Path) -> None:
    """先頭 1 バイトが読めないものは、読めるとは言えない。"""
    (tmp_path / "index.html").write_bytes(b"")

    assert WebDistProbe().check(str(tmp_path)) == MISSING


def test_a_directory_named_index_html_is_abnormal_missing(tmp_path: Path) -> None:
    """通常のファイルでなければ読めない。"""
    (tmp_path / "index.html").mkdir()

    assert WebDistProbe().check(str(tmp_path)) == MISSING


def test_a_broken_symlink_is_abnormal_missing(tmp_path: Path) -> None:
    (tmp_path / "index.html").symlink_to(tmp_path / "no-such-target.html")

    assert WebDistProbe().check(str(tmp_path)) == MISSING


def test_the_index_html_directly_under_the_directory_only_is_checked(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "index.html").write_text("x", encoding="utf-8")

    assert WebDistProbe().check(str(tmp_path)) == MISSING


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read any file")
def test_an_unreadable_index_html_is_abnormal_missing_not_an_exception(tmp_path: Path) -> None:
    index_path = tmp_path / "index.html"
    index_path.write_text("x", encoding="utf-8")
    index_path.chmod(0o000)
    try:
        assert WebDistProbe().check(str(tmp_path)) == MISSING
    finally:
        index_path.chmod(0o644)


def test_the_result_is_not_cached(tmp_path: Path) -> None:
    probe = WebDistProbe()
    assert probe.check(str(tmp_path)) == MISSING

    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    assert probe.check(str(tmp_path)) == NORMAL

    (tmp_path / "index.html").unlink()
    assert probe.check(str(tmp_path)) == MISSING

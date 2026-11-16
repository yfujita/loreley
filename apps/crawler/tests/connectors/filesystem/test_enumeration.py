"""列挙(FS 設計書 4章。10章 #1〜#4・#6〜#10・#12・#13)。一時ディレクトリと偽の `FsOps` で行う。"""

import logging
import os
import shutil
import socket
import stat
from pathlib import Path

import pytest

from loreley_crawler.connectors.filesystem import FileStat
from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    ErrorCategory,
    ErrorScope,
    RetryHint,
)
from tests.connectors.filesystem.support import (
    create_connector,
    drain,
    enumerate_ids,
    enumeration_failure,
    run_with_deadline,
    skip_if_root,
    skip_unless_listed,
    write_file,
)
from tests.fakes.fake_fs_ops import (
    IS_DIR,
    IS_FILE,
    IS_SYMLINK,
    OPEN,
    SCANDIR,
    STAT,
    ScriptedFsOps,
)
from tests.unicode_samples import GA_NFC, GA_NFD

ENUMERATION_LOGGER = "loreley_crawler.connectors.filesystem.enumeration"


# --- #1 既定の拡張子 ---


def test_only_the_default_extensions_are_returned(tmp_path: Path) -> None:
    for name in ["a.txt", "b.md", "c.markdown", "d.html", "e.htm", "f.pdf", "G.PDF", "H.Md"]:
        write_file(tmp_path, name)
    for name in ["i.docx", "noextension", "j.tar.gz", "k.txt.bak", "l.rst", "m."]:
        write_file(tmp_path, name)

    assert enumerate_ids(create_connector(tmp_path)) == {
        "a.txt",
        "b.md",
        "c.markdown",
        "d.html",
        "e.htm",
        "f.pdf",
        "G.PDF",
        "H.Md",
    }


def test_a_name_that_is_only_a_leading_dot_has_no_extension(tmp_path: Path) -> None:
    write_file(tmp_path, ".md")
    write_file(tmp_path, "x/.pdf")
    write_file(tmp_path, ".hidden.md")

    # 隠しファイルを含めても、先頭だけの `.` は拡張子でない(`.md` は対象外)。
    connector = create_connector(tmp_path, include_hidden=True)

    assert enumerate_ids(connector) == {".hidden.md"}


# --- #2 再帰 ---


def test_deep_files_are_returned_with_the_path_relative_to_the_root(tmp_path: Path) -> None:
    write_file(tmp_path, "top.txt")
    write_file(tmp_path, "a/b/c/d/e/deep.md")

    ids = enumerate_ids(create_connector(tmp_path))

    assert ids == {"top.txt", "a/b/c/d/e/deep.md"}
    assert not any(external_id.startswith("/") for external_id in ids)


def test_the_locator_is_the_relative_path_and_size_hint_is_not_given(tmp_path: Path) -> None:
    write_file(tmp_path, "dir/a.txt", b"12345")

    refs, terminal = drain(create_connector(tmp_path).enumerate())

    assert terminal == Completed()
    [ref] = refs
    assert (ref.external_id, ref.locator, ref.size_hint) == ("dir/a.txt", "dir/a.txt", None)


def test_enumeration_can_run_twice_on_the_same_connector(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt")
    connector = create_connector(tmp_path)

    assert enumerate_ids(connector) == enumerate_ids(connector) == {"a.txt"}


# --- #3 include_patterns(既定の拡張子への追加) ---


def test_include_patterns_add_to_the_default_extensions(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt")
    write_file(tmp_path, "docs/b.rst")
    write_file(tmp_path, "c.docx")

    connector = create_connector(tmp_path, include_patterns=["**/*.rst"])

    assert enumerate_ids(connector) == {"a.txt", "docs/b.rst"}


def test_include_patterns_with_a_directory_pattern_include_every_extension(
    tmp_path: Path,
) -> None:
    # 設計上の注意: `docs/**` のようなパターンは、拡張子を問わず配下の全ファイルを対象にする。
    write_file(tmp_path, "docs/a.bin")
    write_file(tmp_path, "docs/sub/b.docx")
    write_file(tmp_path, "other/c.bin")
    write_file(tmp_path, "other/d.txt")

    connector = create_connector(tmp_path, include_patterns=["docs/**"])

    assert enumerate_ids(connector) == {"docs/a.bin", "docs/sub/b.docx", "other/d.txt"}


def test_include_patterns_are_matched_against_the_whole_relative_path(tmp_path: Path) -> None:
    write_file(tmp_path, "a.rst")
    write_file(tmp_path, "x/b.rst")

    connector = create_connector(tmp_path, include_patterns=["*.rst"])

    assert enumerate_ids(connector) == {"a.rst"}


# --- #4 exclude_patterns ---


def test_exclude_patterns_remove_files_and_directories(tmp_path: Path) -> None:
    write_file(tmp_path, "keep.md")
    write_file(tmp_path, "drop.pdf")
    write_file(tmp_path, "archive/a.md")
    write_file(tmp_path, "archive/deep/b.md")
    write_file(tmp_path, "x/lost+found/c.md")
    write_file(tmp_path, "x/ok.md")

    connector = create_connector(
        tmp_path, exclude_patterns=["**/*.pdf", "archive/**", "**/lost+found"]
    )

    assert enumerate_ids(connector) == {"keep.md", "x/ok.md"}


def test_an_excluded_directory_is_never_opened(tmp_path: Path) -> None:
    write_file(tmp_path, "keep.md")
    write_file(tmp_path, "secret/a.md")
    write_file(tmp_path, "secret/deep/b.md")
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs, exclude_patterns=["secret"])

    assert enumerate_ids(connector) == {"keep.md"}

    # 最初の 1 回は `create` のルートの確認(開いて閉じるだけ)。列挙が開いたのは root だけ。
    scanned = [call.key for call in fs.behavior.calls_of(SCANDIR)]
    assert scanned == [str(tmp_path), str(tmp_path)]


@skip_if_root
def test_excluding_an_unreadable_directory_avoids_the_failure(tmp_path: Path) -> None:
    write_file(tmp_path, "keep.md")
    write_file(tmp_path, "locked/a.md")
    (tmp_path / "locked").chmod(0o000)
    try:
        assert enumerate_ids(create_connector(tmp_path, exclude_patterns=["locked"])) == {"keep.md"}
        # 除外しなければ、読めないディレクトリは列挙の失敗になる(#12)。
        assert enumeration_failure(create_connector(tmp_path)).category is (
            ErrorCategory.ENUMERATION_INCOMPLETE
        )
    finally:
        (tmp_path / "locked").chmod(0o755)


def test_exclusion_wins_over_inclusion(tmp_path: Path) -> None:
    write_file(tmp_path, "a.rst")
    write_file(tmp_path, "b.rst")

    connector = create_connector(tmp_path, include_patterns=["*.rst"], exclude_patterns=["b.rst"])

    assert enumerate_ids(connector) == {"a.rst"}


def test_exclude_patterns_apply_to_default_extensions_too(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md")
    write_file(tmp_path, "b.md")

    connector = create_connector(tmp_path, exclude_patterns=["a.md"])

    assert enumerate_ids(connector) == {"b.md"}


# --- #6 隠しファイル ---


def test_hidden_files_and_directories_are_ignored_by_default(tmp_path: Path) -> None:
    write_file(tmp_path, "visible.md")
    write_file(tmp_path, ".hidden.md")
    write_file(tmp_path, ".git/config.md")
    write_file(tmp_path, "sub/.DS_Store.md")
    write_file(tmp_path, "sub/ok.md")

    assert enumerate_ids(create_connector(tmp_path)) == {"visible.md", "sub/ok.md"}


def test_include_hidden_returns_hidden_files_and_walks_hidden_directories(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "visible.md")
    write_file(tmp_path, ".hidden.md")
    write_file(tmp_path, ".git/config.md")

    connector = create_connector(tmp_path, include_hidden=True)

    assert enumerate_ids(connector) == {"visible.md", ".hidden.md", ".git/config.md"}


def test_a_dot_name_above_the_root_does_not_matter(tmp_path: Path) -> None:
    root = tmp_path / ".hidden-parent" / ".root"
    write_file(root, "a.md")

    assert enumerate_ids(create_connector(root)) == {"a.md"}


# --- #7 シンボリックリンク(false) ---


def test_symlinks_are_neither_returned_nor_followed_by_default(tmp_path: Path) -> None:
    root = tmp_path / "root"
    write_file(root, "real.md")
    write_file(root, "dir/inner.md")
    write_file(tmp_path, "outside.md")
    os.symlink(root / "real.md", root / "link-to-file.md")
    os.symlink(root / "dir", root / "link-to-dir")
    os.symlink(tmp_path / "outside.md", root / "link-outside.md")

    assert enumerate_ids(create_connector(root)) == {"real.md", "dir/inner.md"}


def test_a_root_that_is_a_symlink_can_be_enumerated_without_following_links(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "real/a.md")
    os.symlink(tmp_path / "real", tmp_path / "root-link")

    assert enumerate_ids(create_connector(tmp_path / "root-link")) == {"a.md"}


# --- #8 シンボリックリンク(true) ---


def test_links_inside_the_root_are_returned_and_followed(tmp_path: Path) -> None:
    write_file(tmp_path, "real.md")
    write_file(tmp_path, "dir/inner.md")
    os.symlink(tmp_path / "real.md", tmp_path / "link-to-file.md")
    os.symlink(tmp_path / "dir", tmp_path / "link-to-dir")

    ids = enumerate_ids(create_connector(tmp_path, follow_symlinks=True))

    assert ids == {
        "real.md",
        "dir/inner.md",
        "link-to-file.md",
        "link-to-dir/inner.md",  # パスは走査の経路で一意(重複は共通処理が除く)
    }


def test_links_that_cannot_be_followed_are_ignored_and_the_enumeration_completes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    write_file(root, "ok.md")
    write_file(root, "file.txt")
    write_file(tmp_path, "outside/out.md")
    os.symlink(root / "missing-target", root / "broken.md")  # ENOENT
    os.symlink("self-loop", root / "self-loop")  # ELOOP
    os.symlink(root / "file.txt" / "x", root / "through-file")  # ENOTDIR
    os.symlink(tmp_path / "outside", root / "outside-dir")  # root の外
    os.symlink(tmp_path / "outside" / "out.md", root / "outside-file.md")

    assert enumerate_ids(create_connector(root, follow_symlinks=True)) == {"ok.md", "file.txt"}


def test_a_link_to_a_sibling_whose_name_starts_with_the_root_name_is_outside(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    write_file(root, "ok.md")
    write_file(tmp_path, "root-other/secret.md")
    os.symlink(tmp_path / "root-other", root / "sibling-dir")
    os.symlink(tmp_path / "root-other" / "secret.md", root / "sibling-file.md")

    assert enumerate_ids(create_connector(root, follow_symlinks=True)) == {"ok.md"}


def test_links_to_an_ancestor_or_to_the_root_itself_are_ignored(tmp_path: Path) -> None:
    write_file(tmp_path, "a/b/doc.md")
    os.symlink("..", tmp_path / "a" / "b" / "up")  # 祖先へのループ
    os.symlink(".", tmp_path / "self")  # root 自身を指す

    assert enumerate_ids(create_connector(tmp_path, follow_symlinks=True)) == {"a/b/doc.md"}


def test_a_link_to_a_directory_that_is_not_an_ancestor_is_walked_without_looping(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "shared/doc.md")
    os.symlink("shared", tmp_path / "x")
    (tmp_path / "x2").mkdir()
    os.symlink("../shared", tmp_path / "x2" / "again")

    ids = enumerate_ids(create_connector(tmp_path, follow_symlinks=True))

    assert ids == {"shared/doc.md", "x/doc.md", "x2/again/doc.md"}


@skip_if_root
def test_a_link_whose_target_parent_is_not_traversable_fails_the_enumeration(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    write_file(root, "ok.md")
    write_file(root, "locked-inside/target.md")
    os.symlink(root / "locked-inside" / "target.md", root / "link-inside.md")
    (root / "locked-inside").chmod(0o000)
    try:
        failure = enumeration_failure(create_connector(root, follow_symlinks=True))
    finally:
        (root / "locked-inside").chmod(0o755)

    assert failure.category is ErrorCategory.ENUMERATION_INCOMPLETE


def test_an_unexpected_error_on_a_followed_link_fails_the_enumeration(tmp_path: Path) -> None:
    """EACCES など、壊れたリンクの印でない errno は無視せず列挙の失敗にする(権限なしで再現)。"""
    write_file(tmp_path, "real.md")
    os.symlink(tmp_path / "real.md", tmp_path / "link.md")
    fs = ScriptedFsOps()
    fs.behavior.inject(IS_FILE, PermissionError(13, "denied"), key=str(tmp_path / "link.md"))
    connector = create_connector(tmp_path, fs, follow_symlinks=True)

    failure = enumeration_failure(connector)

    assert failure.category is ErrorCategory.ENUMERATION_INCOMPLETE
    assert "EACCES" in failure.message
    assert "link.md" in failure.message


def test_root_slash_treats_every_link_as_inside_and_never_produces_double_slashes(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "docs/a.md")
    write_file(tmp_path, "docs/sub/b.md")
    os.symlink("docs", tmp_path / "link-to-docs")
    fs = ScriptedFsOps(virtual_root=tmp_path)
    connector = create_connector("/", fs, follow_symlinks=True)

    refs, terminal = drain(connector.enumerate())

    assert terminal == Completed()
    assert {ref.external_id for ref in refs} == {
        "docs/a.md",
        "docs/sub/b.md",
        "link-to-docs/a.md",
        "link-to-docs/sub/b.md",
    }
    assert not any("//" in str(ref.locator) or "//" in ref.external_id for ref in refs)
    for ref in refs:
        assert connector.fetch(ref, 100).content == b"content"
    assert not any("//" in str(call.key) for call in fs.behavior.calls if call.key)
    assert "/docs/a.md" in [call.key for call in fs.behavior.calls_of(OPEN)]


def test_root_slash_does_not_produce_double_slashes_without_following_links(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "docs/a.md")
    fs = ScriptedFsOps(virtual_root=tmp_path)

    refs, _ = drain(create_connector("/", fs).enumerate())

    assert [ref.external_id for ref in refs] == ["docs/a.md"]
    # 最初の 1 回は `create` のルートの確認。
    assert [call.key for call in fs.behavior.calls_of(SCANDIR)] == ["/", "/", "/docs"]


# --- #9 通常ファイル以外 ---


def test_fifos_and_sockets_are_not_returned_and_the_enumeration_does_not_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_file(tmp_path, "ok.md")
    os.mkfifo(tmp_path / "pipe.md")
    # ソケットのパスは長さの制限が厳しいので、相対パスで作る。
    monkeypatch.chdir(tmp_path)
    with socket.socket(socket.AF_UNIX) as unix_socket:
        unix_socket.bind("sock.md")

        refs, terminal = run_with_deadline(lambda: drain(create_connector(tmp_path).enumerate()))

    assert terminal == Completed()
    assert [ref.external_id for ref in refs] == ["ok.md"]


# --- #10 Completed と 0 件 ---


def test_an_empty_root_completes_with_no_documents(tmp_path: Path) -> None:
    refs, terminal = drain(create_connector(tmp_path).enumerate())

    assert refs == []
    assert terminal == Completed()


def test_a_root_where_everything_is_out_of_scope_completes_with_no_documents(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "a.docx")
    write_file(tmp_path, ".hidden.md")
    write_file(tmp_path, "skip/b.md")

    refs, terminal = drain(create_connector(tmp_path, exclude_patterns=["skip"]).enumerate())

    assert refs == []
    assert terminal == Completed()


# --- 列挙の終端と close ---


def test_next_after_completed_keeps_returning_completed(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md")
    stream = create_connector(tmp_path).enumerate()
    drain(stream)

    assert stream.next() == Completed()
    assert stream.next() == Completed()


def test_closing_midway_never_completes_the_enumeration(tmp_path: Path) -> None:
    for index in range(5):
        write_file(tmp_path, f"d/{index}.md")
    stream = create_connector(tmp_path).enumerate()
    first = stream.next()

    stream.close()

    assert not isinstance(first, Completed)
    with pytest.raises(RuntimeError):
        stream.next()
    stream.close()  # 繰り返しても例外にならない


def test_a_failed_enumeration_never_turns_into_completed_on_the_next_call(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "ok.md")
    write_file(tmp_path, "sub/a.md")
    fs = ScriptedFsOps()
    fs.behavior.inject(SCANDIR, PermissionError(13, "denied"), key=str(tmp_path / "sub"))
    stream = create_connector(tmp_path, fs).enumerate()

    _, terminal = drain(stream)
    assert isinstance(terminal, ConnectorError)
    for _ in range(2):
        with pytest.raises(ConnectorError) as exc_info:
            stream.next()
        assert exc_info.value is terminal


def test_the_connector_can_fetch_after_the_stream_is_closed(tmp_path: Path) -> None:
    write_file(tmp_path, "a.md", b"hello")
    connector = create_connector(tmp_path)
    stream = connector.enumerate()
    ref = stream.next()
    stream.close()

    assert not isinstance(ref, Completed)
    assert connector.fetch(ref, 100).content == b"hello"
    connector.close()


# --- #12 列挙の失敗 ---


@skip_if_root
def test_an_unreadable_subdirectory_fails_the_enumeration_with_the_path_and_errno(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "ok.md")
    write_file(tmp_path, "docs/locked/a.md")
    (tmp_path / "docs" / "locked").chmod(0o000)
    try:
        failure = enumeration_failure(create_connector(tmp_path))
    finally:
        (tmp_path / "docs" / "locked").chmod(0o755)

    assert failure.category is ErrorCategory.ENUMERATION_INCOMPLETE
    assert failure.scope is ErrorScope.SOURCE
    assert failure.retry is RetryHint.UNKNOWN
    assert "EACCES" in failure.message
    assert "`docs/locked`" in failure.message


def test_a_subdirectory_that_cannot_be_read_fails_the_enumeration_as_root_would_not(
    tmp_path: Path,
) -> None:
    """権限を使わずに(root でも)、配下の失敗が `enumeration_incomplete` になることを確かめる。"""
    write_file(tmp_path, "docs/a.md")
    fs = ScriptedFsOps()
    fs.behavior.inject(SCANDIR, PermissionError(13, "denied"), key=str(tmp_path / "docs"))

    failure = enumeration_failure(create_connector(tmp_path, fs))

    assert failure.category is ErrorCategory.ENUMERATION_INCOMPLETE
    assert "EACCES" in failure.message
    assert "`docs`" in failure.message


def test_a_directory_removed_during_the_walk_fails_the_enumeration(tmp_path: Path) -> None:
    write_file(tmp_path, "docs/a.md")
    fs = ScriptedFsOps()
    # 一覧を得てから開くまでの間に、ディレクトリが消える(マウント外れと区別できない)。
    fs.behavior.before(
        SCANDIR, lambda: shutil.rmtree(tmp_path / "docs"), key=str(tmp_path / "docs")
    )

    failure = enumeration_failure(create_connector(tmp_path, fs))

    assert failure.category is ErrorCategory.ENUMERATION_INCOMPLETE
    assert "ENOENT" in failure.message


def test_a_failure_stops_the_walk_but_documents_found_before_it_were_returned(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "a.md")
    write_file(tmp_path, "docs/b.md")
    fs = ScriptedFsOps()
    fs.behavior.inject(SCANDIR, OSError(5, "io"), key=str(tmp_path / "docs"))

    refs, terminal = drain(create_connector(tmp_path, fs).enumerate())

    assert isinstance(terminal, ConnectorError)
    # 返す順序は規定しない(4.5)ので、失敗の前に `a.md` を返したかどうかは決まらない。
    # 失敗した `docs` の中の文書(`docs/b.md`)だけは、返されない。
    assert {ref.external_id for ref in refs} <= {"a.md"}


def test_the_path_in_the_message_is_escaped_and_truncated(tmp_path: Path) -> None:
    # 1 つの名前は 255 バイトまでなので、3 階層で 200 文字を超えるパスにする。
    directory = "/".join(["x\ny" + "z" * 97, "z" * 100, "z" * 100])
    write_file(tmp_path, f"{directory}/a.md")
    fs = ScriptedFsOps()
    fs.behavior.inject(SCANDIR, OSError(5, "io"), key=str(tmp_path / directory))

    failure = enumeration_failure(create_connector(tmp_path, fs))

    assert "\n" not in failure.message
    assert "x\\ny" in failure.message
    assert "z" * 201 not in failure.message


# --- #13 列挙中に消えたファイル ---


def test_a_file_that_vanishes_before_its_kind_is_checked_is_ignored(tmp_path: Path) -> None:
    write_file(tmp_path, "stays.md")
    vanishing = write_file(tmp_path, "vanishes.md")
    fs = ScriptedFsOps()
    key = str(vanishing)
    # 一覧を得た後、種別を判定する前にファイルが消える。`os.DirEntry` は、消えたエントリの
    # 判定を例外にせず `False` にする。
    fs.behavior.before(IS_SYMLINK, vanishing.unlink, key=key)
    fs.behavior.inject(IS_DIR, False, key=key, times=None)
    fs.behavior.inject(IS_FILE, False, key=key, times=None)

    refs, terminal = drain(create_connector(tmp_path, fs).enumerate())

    assert terminal == Completed()
    assert [ref.external_id for ref in refs] == ["stays.md"]
    assert not vanishing.exists()


# --- ログ(FS 設計書 9.4) ---


def test_a_summary_without_file_names_is_logged_when_the_enumeration_completes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_file(tmp_path, "SECRET-NAME-a.md")
    write_file(tmp_path, "sub/SECRET-NAME-b.md")
    write_file(tmp_path, ".SECRET-NAME-hidden.md")
    write_file(tmp_path, "SECRET-NAME-c.docx")
    write_file(tmp_path, "SECRET-NAME-skipped/d.md")
    connector = create_connector(tmp_path, exclude_patterns=["SECRET-NAME-skipped"])
    caplog.set_level(logging.INFO, logger=ENUMERATION_LOGGER)

    stream = connector.enumerate()
    first = stream.next()
    assert not isinstance(first, Completed)
    assert caplog.records == []  # 終了するまで出さない
    drain(stream)

    [record] = caplog.records
    message = record.getMessage()
    assert record.levelno == logging.INFO
    assert "directories=2" in message  # root と sub(除外したディレクトリは開かない)
    assert "documents=2" in message
    assert "hidden=1" in message
    assert "not_included=1" in message
    assert "excluded=1" in message
    assert "SECRET-NAME" not in message


def test_no_completion_summary_is_logged_for_a_failed_enumeration(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_file(tmp_path, "docs/a.md")
    fs = ScriptedFsOps()
    fs.behavior.inject(SCANDIR, OSError(5, "io"), key=str(tmp_path / "docs"))
    caplog.set_level(logging.INFO, logger=ENUMERATION_LOGGER)

    enumeration_failure(create_connector(tmp_path, fs))

    assert caplog.records == []


# --- #5 列挙側の NFC 化 ---


def test_an_nfc_exclude_pattern_excludes_a_directory_written_in_nfd(tmp_path: Path) -> None:
    write_file(tmp_path, "keep.md")
    write_file(tmp_path, f"{GA_NFD}/inside.md")
    skip_unless_listed(tmp_path, GA_NFD)

    connector = create_connector(tmp_path, exclude_patterns=[f"{GA_NFC}/**"])

    assert enumerate_ids(connector) == {"keep.md"}


def test_an_nfc_include_pattern_picks_up_a_file_written_in_nfd(tmp_path: Path) -> None:
    write_file(tmp_path, f"{GA_NFD}.rst")
    skip_unless_listed(tmp_path, f"{GA_NFD}.rst")

    connector = create_connector(tmp_path, include_patterns=[f"{GA_NFC}.rst"])

    # `external_id` は OS の名前のまま(NFC にするのは共通処理)。
    assert enumerate_ids(connector) == {f"{GA_NFD}.rst"}


# --- パターンはルートからの相対パス全体に当たる ---


def test_a_single_segment_exclude_pattern_only_matches_directly_under_the_root(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "a.md")
    write_file(tmp_path, "sub/a.md")
    write_file(tmp_path, "sub/deep/b.md")

    assert enumerate_ids(create_connector(tmp_path, exclude_patterns=["*.md"])) == {
        "sub/a.md",
        "sub/deep/b.md",
    }


def test_a_multi_segment_exclude_pattern_matches_the_whole_relative_path(tmp_path: Path) -> None:
    write_file(tmp_path, "docs/x.tmp.md")
    write_file(tmp_path, "docs/y.md")
    write_file(tmp_path, "other/docs/x.tmp.md")

    connector = create_connector(tmp_path, exclude_patterns=["docs/*.tmp.md"])

    assert enumerate_ids(connector) == {"docs/y.md", "other/docs/x.tmp.md"}


def test_an_exclude_pattern_matches_names_that_contain_a_newline(tmp_path: Path) -> None:
    write_file(tmp_path, "docs/line\nbreak.md")
    write_file(tmp_path, "docs/plain.md")
    write_file(tmp_path, "keep\nme.md")
    write_file(tmp_path, "other\nname/inside.md")

    # `*` と `?` が、改行を含む名前の改行に当たる(ファイルとディレクトリの両方)。
    connector = create_connector(tmp_path, exclude_patterns=["docs/line*.md", "other?name"])

    assert enumerate_ids(connector) == {"docs/plain.md", "keep\nme.md"}


# --- scandir は読み切って閉じる(4.5・9.2) ---


def test_scandir_is_read_to_the_end_and_closed_before_descending(tmp_path: Path) -> None:
    for depth in range(10):
        prefix = "/".join(f"level{index}" for index in range(depth + 1))
        write_file(tmp_path, f"{prefix}/doc{depth}.md")
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs)

    ids = enumerate_ids(connector)

    assert len(ids) == 10
    # 同時に開く scandir は 1 つだけ(開いたまま子へ下りない)。`create` の確認も含めて 1。
    assert fs.max_open_scandir_count == 1
    assert fs.open_scandir_count == 0


def test_no_scandir_stays_open_after_a_failed_or_closed_enumeration(tmp_path: Path) -> None:
    write_file(tmp_path, "a/b/c.md")
    write_file(tmp_path, "z/x.md")
    fs = ScriptedFsOps()
    fs.behavior.inject(SCANDIR, OSError(5, "io"), key=str(tmp_path / "a" / "b"))
    connector = create_connector(tmp_path, fs)
    enumeration_failure(connector)
    assert fs.open_scandir_count == 0

    stream = create_connector(tmp_path, fs).enumerate()
    stream.next()
    stream.close()

    assert fs.open_scandir_count == 0
    assert fs.max_open_scandir_count == 1


# --- 祖先ループの判定は (st_dev, st_ino) の組 ---


def test_a_link_to_a_directory_with_the_same_inode_on_another_device_is_not_a_loop(
    tmp_path: Path,
) -> None:
    write_file(tmp_path, "a/b/doc.md")
    link = tmp_path / "a" / "b" / "up"
    os.symlink("..", link)
    fs = ScriptedFsOps()
    real = fs.stat(str(tmp_path / "a"))
    # `up` は `a` と同じ inode だが、別のデバイスにあるように見せる(別の共有の同じ inode 番号)。
    other_device = FileStat(stat.S_IFDIR | 0o755, 0, 0, real.device + 1, real.inode)
    fs.behavior.inject(STAT, other_device, key=str(link))

    ids = enumerate_ids(create_connector(tmp_path, fs, follow_symlinks=True))

    # 別デバイスなら祖先ではないので、`up`(= `a`)の中も走査される(inode だけでは区別できない)。
    assert "a/b/up/b/doc.md" in ids
    assert "a/b/doc.md" in ids

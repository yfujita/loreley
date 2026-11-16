"""取得(FS 設計書 5章・6章。10章 #14〜#17・#22)。"""

import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from loreley_crawler.connectors.filesystem import FileStat, FileSystemSettings
from loreley_crawler.connectors.filesystem.fetch import mime_type_of
from loreley_crawler.connectors.interface import (
    Connector,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
    ErrorScope,
    RetryHint,
)
from tests.connectors.filesystem.support import (
    create_connector,
    run_with_deadline,
    skip_if_root,
    write_file,
)
from tests.fakes.fake_fs_ops import FSTAT, OPEN, READ, ScriptedFsOps
from tests.unicode_samples import GA_NFC, GA_NFD

MAX_BYTES = 1024


def ref_of(relative_path: str) -> DocumentRef:
    return DocumentRef(external_id=relative_path, locator=relative_path)


def fetch_failure(
    connector: Connector, relative_path: str, max_bytes: int = MAX_BYTES
) -> ConnectorError:
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(ref_of(relative_path), max_bytes)
    return exc_info.value


# --- #14 取得 ---


def test_the_content_is_returned_as_it_is(tmp_path: Path) -> None:
    content = bytes(range(256)) * 3
    write_file(tmp_path, "a.txt", content)

    fetched = create_connector(tmp_path).fetch(ref_of("a.txt"), MAX_BYTES)

    assert fetched.content == content


def test_the_metadata_follows_the_design(tmp_path: Path) -> None:
    path = write_file(tmp_path, "dir/Report.PDF", b"%PDF-")
    mtime_ns = 1_700_000_000_123_456_789
    os.utime(path, ns=(mtime_ns, mtime_ns))

    metadata = create_connector(tmp_path).fetch(ref_of("dir/Report.PDF"), MAX_BYTES).metadata

    assert metadata.title == "Report.PDF"  # 拡張子を含み、ディレクトリを含まない
    assert metadata.path == "dir/Report.PDF"
    assert metadata.mime_type == "application/pdf"
    assert metadata.url is None
    # ナノ秒からマイクロ秒への変換は切り捨て。
    assert metadata.source_updated_at == datetime(2023, 11, 14, 22, 13, 20, 123456, tzinfo=UTC)
    assert metadata.source_updated_at.utcoffset() is not None


@pytest.mark.parametrize(
    ("file_name", "mime_type"),
    [
        ("a.txt", "text/plain"),
        ("a.md", "text/markdown"),
        ("a.markdown", "text/markdown"),
        ("a.html", "text/html"),
        ("a.htm", "text/html"),
        ("a.pdf", "application/pdf"),
        ("A.PDF", "application/pdf"),
        ("a.rst", "application/octet-stream"),  # include_patterns で追加した拡張子
        ("noextension", "application/octet-stream"),
        ("a.tar.gz", "application/octet-stream"),
    ],
)
def test_mime_types_follow_the_extension_table(file_name: str, mime_type: str) -> None:
    assert mime_type_of(file_name) == mime_type


def test_an_added_extension_is_fetched_as_octet_stream_without_rejection(tmp_path: Path) -> None:
    write_file(tmp_path, "doc/a.rst", b"title\n=====")

    fetched = create_connector(tmp_path, include_patterns=["**/*.rst"]).fetch(
        ref_of("doc/a.rst"), MAX_BYTES
    )

    assert fetched.metadata.mime_type == "application/octet-stream"
    assert fetched.content == b"title\n====="


@pytest.mark.parametrize(
    "mtime_ns",
    [
        10**30,  # timedelta が扱えない大きさ(OverflowError)
        253_402_300_800 * 10**9,  # 年が 10000(日時として表せない)
        -62_135_596_801 * 10**9,  # 年が 0
    ],
)
def test_an_mtime_that_is_not_representable_becomes_the_fixed_epoch(
    tmp_path: Path, mtime_ns: int
) -> None:
    path = write_file(tmp_path, "a.txt", b"abc")
    fs = ScriptedFsOps()
    unrepresentable = FileStat(stat.S_IFREG | 0o644, 3, mtime_ns, 1, 1)
    fs.behavior.inject(FSTAT, unrepresentable, key=str(path), times=None)

    metadata = create_connector(tmp_path, fs).fetch(ref_of("a.txt"), MAX_BYTES).metadata

    assert metadata.source_updated_at == datetime(1970, 1, 1, tzinfo=UTC)


def test_an_mtime_before_1970_is_kept(tmp_path: Path) -> None:
    path = write_file(tmp_path, "a.txt")
    os.utime(path, ns=(-1_000_000_000, -1_000_000_000))

    metadata = create_connector(tmp_path).fetch(ref_of("a.txt"), MAX_BYTES).metadata

    assert metadata.source_updated_at == datetime(1969, 12, 31, 23, 59, 59, tzinfo=UTC)


def test_the_same_ref_can_be_fetched_twice_and_the_original_is_not_changed(
    tmp_path: Path,
) -> None:
    path = write_file(tmp_path, "a.txt", b"original")
    before = (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_size)
    connector = create_connector(tmp_path)

    first = connector.fetch(ref_of("a.txt"), MAX_BYTES)
    second = connector.fetch(ref_of("a.txt"), MAX_BYTES)

    assert first == second
    assert (path.read_bytes(), path.stat().st_mtime_ns, path.stat().st_size) == before


def test_an_empty_file_is_fetched(tmp_path: Path) -> None:
    write_file(tmp_path, "empty.txt", b"")

    assert create_connector(tmp_path).fetch(ref_of("empty.txt"), MAX_BYTES).content == b""
    assert create_connector(tmp_path).fetch(ref_of("empty.txt"), 0).content == b""


def test_title_and_path_are_nfc_and_the_name_is_otherwise_kept(tmp_path: Path) -> None:
    nfd_name = f"{GA_NFD}.txt"
    path = tmp_path / nfd_name
    path.write_bytes(b"x")
    if nfd_name not in os.listdir(tmp_path):
        pytest.skip("this file system normalizes file names, so an NFD name cannot be created")

    metadata = create_connector(tmp_path).fetch(ref_of(nfd_name), MAX_BYTES).metadata
    assert metadata.title == f"{GA_NFC}.txt"
    assert metadata.path == f"{GA_NFC}.txt"
    assert metadata.path == "が.txt"


def test_a_name_with_a_backslash_newline_and_tab_is_fetched_and_kept_in_title_and_path(
    tmp_path: Path,
) -> None:
    name = "a\\b\nc\td.txt"
    write_file(tmp_path, name, b"x")

    metadata = create_connector(tmp_path).fetch(ref_of(name), MAX_BYTES).metadata

    assert metadata.title == name
    assert metadata.path == name


# --- #15 oversize ---


def test_a_file_larger_than_the_limit_is_oversize_without_reading_it(tmp_path: Path) -> None:
    path = write_file(tmp_path, "big.txt", b"x" * 11)
    fs = ScriptedFsOps()

    error = fetch_failure(create_connector(tmp_path, fs), "big.txt", max_bytes=10)

    assert error.category is ErrorCategory.OVERSIZE
    assert error.scope is ErrorScope.DOCUMENT
    assert error.retry is RetryHint.PERMANENT
    assert fs.behavior.calls_of(READ) == []
    assert fs.behavior.calls_of(OPEN)[0].key == str(path)


def test_a_file_of_exactly_the_limit_is_fetched(tmp_path: Path) -> None:
    write_file(tmp_path, "exact.txt", b"x" * 10)

    assert create_connector(tmp_path).fetch(ref_of("exact.txt"), 10).content == b"x" * 10


def test_a_file_that_grows_while_being_read_is_oversize_and_not_read_to_the_end(
    tmp_path: Path,
) -> None:
    path = write_file(tmp_path, "growing.txt", b"x" * 10)
    fs = ScriptedFsOps()
    key = str(path)

    def grow() -> None:
        path.write_bytes(b"y" * 10_000)

    fs.behavior.before(READ, grow, key=key)
    connector = create_connector(tmp_path, fs, settings=FileSystemSettings(read_chunk_bytes=4))

    error = fetch_failure(connector, "growing.txt", max_bytes=10)

    assert error.category is ErrorCategory.OVERSIZE
    # `max_bytes + 1` = 11 バイトまでしか読まない(4 + 4 + 3)。
    assert len(fs.behavior.calls_of(READ)) == 3


def test_the_read_never_asks_for_more_than_one_byte_over_the_limit(tmp_path: Path) -> None:
    path = write_file(tmp_path, "growing.txt", b"x" * 10)
    fs = ScriptedFsOps()
    fs.behavior.before(READ, lambda: path.write_bytes(b"y" * 10_000), key=str(path))
    connector = create_connector(tmp_path, fs, settings=FileSystemSettings(read_chunk_bytes=4))

    fetch_failure(connector, "growing.txt", max_bytes=10)

    assert fs.bytes_read == 11  # max_bytes + 1(超えたことを知る最小の量)


def test_a_one_byte_file_is_oversize_when_the_limit_is_zero(tmp_path: Path) -> None:
    write_file(tmp_path, "one.txt", b"x")
    write_file(tmp_path, "zero.txt", b"")
    connector = create_connector(tmp_path)

    assert fetch_failure(connector, "one.txt", max_bytes=0).category is ErrorCategory.OVERSIZE
    assert connector.fetch(ref_of("zero.txt"), 0).content == b""


def test_a_file_that_grows_from_empty_to_one_byte_is_oversize_when_the_limit_is_zero(
    tmp_path: Path,
) -> None:
    path = write_file(tmp_path, "empty.txt", b"")
    fs = ScriptedFsOps()
    fs.behavior.before(READ, lambda: path.write_bytes(b"x" * 100), key=str(path))

    error = fetch_failure(create_connector(tmp_path, fs), "empty.txt", max_bytes=0)

    assert error.category is ErrorCategory.OVERSIZE
    assert fs.bytes_read == 1


def test_the_content_is_read_in_chunks_of_the_configured_size(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt", b"0123456789")
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs, settings=FileSystemSettings(read_chunk_bytes=4))

    fetched = connector.fetch(ref_of("a.txt"), MAX_BYTES)

    assert fetched.content == b"0123456789"
    # 4 + 4 + 2 に、ファイルの終わりを確かめる 1 回(空の読み取り)。
    assert len(fs.behavior.calls_of(READ)) == 4


def test_a_negative_limit_is_a_programming_error(tmp_path: Path) -> None:
    write_file(tmp_path, "a.txt")

    with pytest.raises(ValueError, match="max_bytes"):
        create_connector(tmp_path).fetch(ref_of("a.txt"), -1)


# --- #16 取得の失敗 ---


def test_a_file_deleted_after_the_enumeration_is_fetch_not_found(tmp_path: Path) -> None:
    path = write_file(tmp_path, "gone.txt")
    connector = create_connector(tmp_path)
    path.unlink()

    error = fetch_failure(connector, "gone.txt")

    assert error.category is ErrorCategory.FETCH_NOT_FOUND
    assert error.scope is ErrorScope.DOCUMENT
    assert error.retry is RetryHint.PERMANENT
    assert "ENOENT" in error.message


@skip_if_root
def test_an_unreadable_file_is_fetch_permission_denied(tmp_path: Path) -> None:
    path = write_file(tmp_path, "locked.txt")
    path.chmod(0o000)
    try:
        error = fetch_failure(create_connector(tmp_path), "locked.txt")
    finally:
        path.chmod(0o644)

    assert error.category is ErrorCategory.FETCH_PERMISSION_DENIED
    assert error.retry is RetryHint.PERMANENT
    assert "EACCES" in error.message


def test_a_file_replaced_by_a_directory_is_fetch_not_found(tmp_path: Path) -> None:
    path = write_file(tmp_path, "swapped.txt")
    connector = create_connector(tmp_path)
    path.unlink()
    path.mkdir()

    assert fetch_failure(connector, "swapped.txt").category is ErrorCategory.FETCH_NOT_FOUND


def test_a_file_replaced_by_a_symlink_is_fetch_not_found_unless_links_are_followed(
    tmp_path: Path,
) -> None:
    path = write_file(tmp_path, "swapped.txt", b"original")
    write_file(tmp_path, "other.txt", b"other")
    path.unlink()
    os.symlink(tmp_path / "other.txt", path)

    error = fetch_failure(create_connector(tmp_path), "swapped.txt")

    assert error.category is ErrorCategory.FETCH_NOT_FOUND
    assert "ELOOP" in error.message
    followed = create_connector(tmp_path, follow_symlinks=True).fetch(ref_of("swapped.txt"), 100)
    assert followed.content == b"other"


def test_a_file_replaced_by_a_fifo_is_fetch_not_found_and_does_not_block(
    tmp_path: Path,
) -> None:
    path = write_file(tmp_path, "swapped.txt")
    connector = create_connector(tmp_path)
    path.unlink()
    os.mkfifo(path)

    error = run_with_deadline(lambda: fetch_failure(connector, "swapped.txt"))

    assert error.category is ErrorCategory.FETCH_NOT_FOUND


def test_a_directory_link_in_the_middle_of_a_locator_is_followed_by_design(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    write_file(tmp_path, "outside/secret.txt", b"secret")
    root.mkdir()
    os.symlink(tmp_path / "outside", root / "dir-link")

    # 最後の構成要素でない(途中の)リンクは `O_NOFOLLOW` では防げない。列挙が返さない道で、
    # 共有への書き込み権限を持つ者に限られるため、MVP の信頼の前提で許容する(FS 4.2)。
    # ここでは、許容している挙動(読めてしまうこと)が変わったときに気づくために固定する。
    fetched = create_connector(root).fetch(ref_of("dir-link/secret.txt"), 100)

    assert fetched.content == b"secret"


# --- #17 取得中の変更 ---


def test_a_size_change_while_reading_is_fetch_transient(tmp_path: Path) -> None:
    path = write_file(tmp_path, "a.txt", b"before")
    fs = ScriptedFsOps()
    fs.behavior.before(READ, lambda: path.write_bytes(b"after-longer"), key=str(path))

    error = fetch_failure(create_connector(tmp_path, fs), "a.txt")

    assert error.category is ErrorCategory.FETCH_TRANSIENT
    assert error.scope is ErrorScope.DOCUMENT
    assert error.retry is RetryHint.TRANSIENT


def test_a_size_only_change_while_reading_is_fetch_transient(tmp_path: Path) -> None:
    path = write_file(tmp_path, "a.txt", b"original")
    original_mtime_ns = path.stat().st_mtime_ns
    fs = ScriptedFsOps()

    def change_size_but_restore_mtime() -> None:
        path.write_bytes(b"original-and-longer")
        os.utime(path, ns=(original_mtime_ns, original_mtime_ns))

    fs.behavior.before(READ, change_size_but_restore_mtime, key=str(path))

    error = fetch_failure(create_connector(tmp_path, fs), "a.txt")

    assert path.stat().st_mtime_ns == original_mtime_ns  # サイズだけが変わった状態になっている
    assert error.category is ErrorCategory.FETCH_TRANSIENT


def test_an_mtime_only_change_while_reading_is_fetch_transient(tmp_path: Path) -> None:
    path = write_file(tmp_path, "a.txt", b"same-size")
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    fs = ScriptedFsOps()
    fs.behavior.before(
        READ, lambda: os.utime(path, ns=(2_000_000_000, 2_000_000_000)), key=str(path)
    )

    assert fetch_failure(create_connector(tmp_path, fs), "a.txt").category is (
        ErrorCategory.FETCH_TRANSIENT
    )


def test_a_read_that_disagrees_with_the_size_is_fetch_transient(tmp_path: Path) -> None:
    path = write_file(tmp_path, "a.txt", b"12345")
    fs = ScriptedFsOps()
    fs.behavior.inject(READ, b"123", key=str(path))  # fstat の大きさ(5)より短い内容

    assert fetch_failure(create_connector(tmp_path, fs), "a.txt").category is (
        ErrorCategory.FETCH_TRANSIENT
    )


def test_a_retry_after_the_change_succeeds(tmp_path: Path) -> None:
    path = write_file(tmp_path, "a.txt", b"before")
    fs = ScriptedFsOps()
    fs.behavior.before(READ, lambda: path.write_bytes(b"after-longer"), key=str(path))
    connector = create_connector(tmp_path, fs)
    fetch_failure(connector, "a.txt")

    assert connector.fetch(ref_of("a.txt"), MAX_BYTES).content == b"after-longer"


# --- #22 locator の検査 ---


@pytest.mark.parametrize(
    "locator", ["../outside.txt", "a/../../outside.txt", "..", "/etc/passwd", "a\x00b.txt"]
)
def test_a_locator_that_could_leave_the_root_is_fetch_not_found_without_opening(
    tmp_path: Path, locator: str
) -> None:
    fs = ScriptedFsOps()

    error = fetch_failure(create_connector(tmp_path, fs), locator)

    assert error.category is ErrorCategory.FETCH_NOT_FOUND
    assert error.scope is ErrorScope.DOCUMENT
    assert fs.behavior.calls_of(OPEN) == []


def test_a_locator_that_only_contains_dots_in_a_name_is_allowed(tmp_path: Path) -> None:
    write_file(tmp_path, "..hidden/a..b.txt", b"x")

    assert create_connector(tmp_path).fetch(ref_of("..hidden/a..b.txt"), 10).content == b"x"


def test_a_locator_that_is_not_a_string_is_a_programming_error(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        create_connector(tmp_path).fetch(DocumentRef("a.txt", locator=b"a.txt"), 10)


# --- 説明文に本文が入らない・パスが切り詰められる ---

SECRET_BODY = b"SECRET-BODY"


def test_the_oversize_message_never_contains_the_body(tmp_path: Path) -> None:
    write_file(tmp_path, "big.txt", SECRET_BODY * 10)

    error = fetch_failure(create_connector(tmp_path), "big.txt", max_bytes=10)

    assert error.category is ErrorCategory.OVERSIZE
    assert "`big.txt`" in error.message
    assert "SECRET-BODY" not in error.message


def test_the_transient_message_never_contains_the_body(tmp_path: Path) -> None:
    changing = write_file(tmp_path, "changing.txt", SECRET_BODY)
    fs = ScriptedFsOps()
    fs.behavior.before(READ, lambda: changing.write_bytes(SECRET_BODY * 2), key=str(changing))

    error = fetch_failure(create_connector(tmp_path, fs), "changing.txt")

    assert error.category is ErrorCategory.FETCH_TRANSIENT
    assert "`changing.txt`" in error.message
    assert "SECRET-BODY" not in error.message


def test_the_permission_denied_message_never_contains_the_body(tmp_path: Path) -> None:
    denied = write_file(tmp_path, "denied.txt", SECRET_BODY)
    fs = ScriptedFsOps()
    # 権限を使わずに(root でも)再現する。
    fs.behavior.inject(OPEN, PermissionError(13, "denied"), key=str(denied))

    error = fetch_failure(create_connector(tmp_path, fs), "denied.txt")

    assert error.category is ErrorCategory.FETCH_PERMISSION_DENIED
    assert "`denied.txt`" in error.message
    assert "SECRET-BODY" not in error.message


def test_the_path_in_a_fetch_message_is_escaped_and_truncated_to_200_characters(
    tmp_path: Path,
) -> None:
    # 1 つの名前は 255 バイトまでなので、3 階層で 200 文字を超えるパスにする(存在しない)。
    relative_path = "/".join(["x\ny" + "z" * 97, "z" * 100, "z" * 100, "a.txt"])

    error = fetch_failure(create_connector(tmp_path), relative_path)

    assert error.category is ErrorCategory.FETCH_NOT_FOUND
    shown = error.message.split("`")[1]
    assert len(shown) == 200
    assert "\n" not in error.message
    assert "x\\ny" in shown
    assert "z" * 200 not in shown  # 先頭の 200 文字だけ(`x\\ny` + `z`)

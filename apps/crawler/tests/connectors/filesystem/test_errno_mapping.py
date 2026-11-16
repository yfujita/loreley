"""errno と分類名の対応(FS 設計書 7.1。10章 #20)。`OSError` の模擬で確かめる。"""

import errno
from pathlib import Path

import pytest

from loreley_crawler.connectors.filesystem import FileSystemConnectorType
from loreley_crawler.connectors.filesystem.errors import UNREACHABLE_ERRNOS
from loreley_crawler.connectors.interface import (
    Connector,
    ConnectorError,
    DocumentRef,
    ErrorCategory,
    ErrorScope,
    RetryHint,
)
from tests.connectors.filesystem.support import SOURCE_ID, create_connector, drain, write_file
from tests.error_text import logged_text
from tests.fakes.fake_fs_ops import IS_DIR, OPEN, READ, SCANDIR, STAT, ScriptedFsOps

# 集合 T(FS 設計書 7.1)。
SET_T = [
    errno.EIO,
    errno.ESTALE,
    errno.ETIMEDOUT,
    errno.ENOTCONN,
    errno.EHOSTDOWN,
    errno.EHOSTUNREACH,
    errno.ENETDOWN,
    errno.ENETUNREACH,
    errno.ECONNREFUSED,
    errno.ECONNRESET,
    errno.ECONNABORTED,
    errno.ENODEV,
    errno.EBUSY,
]
ROOT_NOT_FOUND = [errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.ENAMETOOLONG]
DENIED = [errno.EACCES, errno.EPERM]


def available(*names: str) -> list[int]:
    """この OS にある errno だけ(`ENOMEDIUM` などは Linux にしかない)。"""
    return [getattr(errno, name) for name in names if hasattr(errno, name)]


# 表にない errno は分類しない。root 用と fetch 用で、表に載る集合が違う(7.1)ので分ける。
# `EISDIR` は fetch では「見つからない」だが root では未分類、`ENAMETOOLONG` はその逆。
ROOT_UNCLASSIFIED = available("ENOSPC", "EMFILE", "EINVAL", "EROFS", "EISDIR", "ENXIO", "ENOMEDIUM")
FETCH_UNCLASSIFIED = available(
    "ENOSPC", "EMFILE", "EINVAL", "EROFS", "ENAMETOOLONG", "ENXIO", "ENOMEDIUM"
)


def test_the_set_t_of_the_implementation_is_the_set_of_the_design() -> None:
    assert set(SET_T) == UNREACHABLE_ERRNOS


def raising_root_ops(code: int, root: Path) -> ScriptedFsOps:
    fs = ScriptedFsOps()
    fs.behavior.inject(STAT, OSError(code, "injected"), key=str(root))
    return fs


def create_error(fs: ScriptedFsOps, root: Path) -> ConnectorError:
    with pytest.raises(ConnectorError) as exc_info:
        FileSystemConnectorType(fs).create(SOURCE_ID, {"root": str(root)})
    return exc_info.value


# 列挙の `root` の読み取りの失敗を起こす場所(`follow_symlinks`、操作)。`follow_symlinks=true` の
# ときは、列挙の最初に `root` の `stat`(祖先ループの判定用)も行う。
ROOT_FAILURE_SITES = [(False, SCANDIR), (True, SCANDIR), (True, STAT)]


def enumeration_root_failures(code: int, root: Path) -> list[BaseException]:
    failures: list[BaseException] = []
    for follow_symlinks, operation in ROOT_FAILURE_SITES:
        fs = ScriptedFsOps()
        connector = create_connector(root, fs, follow_symlinks=follow_symlinks)
        # create の後(列挙の最初の `root` の読み取り)で失敗させる。
        fs.behavior.inject(operation, OSError(code, "injected"), key=str(root))
        try:
            _, terminal = drain(connector.enumerate())
        except OSError as error:  # 分類されない errno は、そのまま送出される
            failures.append(error)
        else:
            assert isinstance(terminal, ConnectorError)
            failures.append(terminal)
    return failures


@pytest.mark.parametrize("code", ROOT_NOT_FOUND)
def test_root_errors_that_mean_the_path_does_not_exist_are_source_not_found(
    tmp_path: Path, code: int
) -> None:
    for error in (
        create_error(raising_root_ops(code, tmp_path), tmp_path),
        *enumeration_root_failures(code, tmp_path),
    ):
        assert (error.category, error.scope, error.retry) == (
            ErrorCategory.SOURCE_NOT_FOUND,
            ErrorScope.SOURCE,
            RetryHint.PERMANENT,
        )
        assert errno.errorcode[code] in error.message


@pytest.mark.parametrize("code", DENIED)
def test_root_permission_errors_are_source_access_denied(tmp_path: Path, code: int) -> None:
    for error in (
        create_error(raising_root_ops(code, tmp_path), tmp_path),
        *enumeration_root_failures(code, tmp_path),
    ):
        assert (error.category, error.scope, error.retry) == (
            ErrorCategory.SOURCE_ACCESS_DENIED,
            ErrorScope.SOURCE,
            RetryHint.PERMANENT,
        )


@pytest.mark.parametrize("code", SET_T)
def test_root_errors_of_the_set_t_are_a_transient_source_unreachable(
    tmp_path: Path, code: int
) -> None:
    for error in (
        create_error(raising_root_ops(code, tmp_path), tmp_path),
        *enumeration_root_failures(code, tmp_path),
    ):
        assert (error.category, error.scope, error.retry) == (
            ErrorCategory.SOURCE_UNREACHABLE,
            ErrorScope.SOURCE,
            RetryHint.TRANSIENT,
        )
        assert errno.errorcode[code] in error.message


@pytest.mark.parametrize("code", ROOT_UNCLASSIFIED)
def test_unclassified_root_errors_are_raised_as_the_original_os_error(
    tmp_path: Path, code: int
) -> None:
    fs = raising_root_ops(code, tmp_path)

    with pytest.raises(OSError) as exc_info:
        FileSystemConnectorType(fs).create(SOURCE_ID, {"root": str(tmp_path)})

    assert not isinstance(exc_info.value, ConnectorError)
    assert exc_info.value.errno == code


@pytest.mark.parametrize("code", ROOT_UNCLASSIFIED)
def test_unclassified_errors_on_the_enumeration_root_are_raised_as_they_are(
    tmp_path: Path, code: int
) -> None:
    failures = enumeration_root_failures(code, tmp_path)

    assert len(failures) == len(ROOT_FAILURE_SITES)
    for failure in failures:
        assert isinstance(failure, OSError)
        assert not isinstance(failure, ConnectorError)
        assert failure.errno == code


def fetch_error_for(code: int, tmp_path: Path, operation: str) -> ConnectorError:
    path = write_file(tmp_path, "a.txt", b"content")
    fs = ScriptedFsOps()
    connector: Connector = create_connector(tmp_path, fs)
    fs.behavior.inject(operation, OSError(code, "injected"), key=str(path))
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(DocumentRef("a.txt", "a.txt"), 100)
    return exc_info.value


@pytest.mark.parametrize("operation", [OPEN, READ])
@pytest.mark.parametrize("code", [errno.ENOENT, errno.ENOTDIR, errno.EISDIR, errno.ELOOP])
def test_fetch_errors_that_mean_the_file_is_gone_are_fetch_not_found(
    tmp_path: Path, code: int, operation: str
) -> None:
    error = fetch_error_for(code, tmp_path, operation)

    assert (error.category, error.scope, error.retry) == (
        ErrorCategory.FETCH_NOT_FOUND,
        ErrorScope.DOCUMENT,
        RetryHint.PERMANENT,
    )
    assert errno.errorcode[code] in error.message
    assert "`a.txt`" in error.message


@pytest.mark.parametrize("operation", [OPEN, READ])
@pytest.mark.parametrize("code", DENIED)
def test_fetch_permission_errors_are_fetch_permission_denied(
    tmp_path: Path, code: int, operation: str
) -> None:
    error = fetch_error_for(code, tmp_path, operation)

    assert (error.category, error.scope, error.retry) == (
        ErrorCategory.FETCH_PERMISSION_DENIED,
        ErrorScope.DOCUMENT,
        RetryHint.PERMANENT,
    )


@pytest.mark.parametrize("operation", [OPEN, READ])
@pytest.mark.parametrize("code", SET_T)
def test_fetch_errors_of_the_set_t_are_a_transient_fetch_transient(
    tmp_path: Path, code: int, operation: str
) -> None:
    error = fetch_error_for(code, tmp_path, operation)

    assert (error.category, error.scope, error.retry) == (
        ErrorCategory.FETCH_TRANSIENT,
        ErrorScope.DOCUMENT,
        RetryHint.TRANSIENT,
    )


@pytest.mark.parametrize("code", FETCH_UNCLASSIFIED)
def test_unclassified_fetch_errors_are_raised_as_the_original_os_error(
    tmp_path: Path, code: int
) -> None:
    path = write_file(tmp_path, "a.txt", b"content")
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs)
    fs.behavior.inject(OPEN, OSError(code, "injected"), key=str(path))

    with pytest.raises(OSError) as exc_info:
        connector.fetch(DocumentRef("a.txt", "a.txt"), 100)

    assert not isinstance(exc_info.value, ConnectorError)
    assert exc_info.value.errno == code


def test_the_file_is_closed_even_when_a_read_fails(tmp_path: Path) -> None:
    path = write_file(tmp_path, "a.txt", b"content")
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs)
    fs.behavior.inject(READ, OSError(errno.EIO, "io"), key=str(path))

    with pytest.raises(ConnectorError):
        connector.fetch(DocumentRef("a.txt", "a.txt"), 100)

    operations = [call.operation for call in fs.behavior.calls_of(OPEN, READ, "close")]
    assert operations == [OPEN, READ, "close"]


@pytest.mark.parametrize("code", [*SET_T, errno.ENOENT, errno.EACCES, errno.ENOSPC])
def test_any_os_error_below_the_root_fails_the_enumeration(tmp_path: Path, code: int) -> None:
    write_file(tmp_path, "docs/a.md")
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs)
    fs.behavior.inject(SCANDIR, OSError(code, "injected"), key=str(tmp_path / "docs"))

    _, terminal = drain(connector.enumerate())

    assert isinstance(terminal, ConnectorError)
    assert (terminal.category, terminal.scope, terminal.retry) == (
        ErrorCategory.ENUMERATION_INCOMPLETE,
        ErrorScope.SOURCE,
        RetryHint.UNKNOWN,
    )
    assert "`docs`" in terminal.message


# --- 分類した例外が、元の OSError を連鎖に残さない(R11) ---


def test_classified_errors_do_not_leak_the_original_os_error_into_the_logged_traceback(
    tmp_path: Path,
) -> None:
    """`OSError` はファイル名の repr(制御文字を含みうる未加工のパス)を持つ。ログに出さない。

    必要な情報(errno 名と、切り詰め・エスケープ済みのパス)は説明文にある。
    """

    def injected() -> OSError:
        return OSError(errno.EIO, "io SENTINEL-MESSAGE", "/SENTINEL-FILENAME\nforged line")

    write_file(tmp_path, "sub/a.md", b"x")
    write_file(tmp_path, "sub/b.md", b"x")
    errors: list[ConnectorError] = []

    # create の root の確認
    fs = ScriptedFsOps()
    fs.behavior.inject(STAT, injected(), key=str(tmp_path))
    errors.append(create_error(fs, tmp_path))
    # 列挙の root と、root 以外のディレクトリの読み取り
    for directory in (tmp_path, tmp_path / "sub"):
        fs = ScriptedFsOps()
        connector = create_connector(tmp_path, fs)
        fs.behavior.inject(SCANDIR, injected(), key=str(directory))
        _, terminal = drain(connector.enumerate())
        assert isinstance(terminal, ConnectorError)
        errors.append(terminal)
    # 列挙のループ内(エントリの種別の判定)
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs)
    fs.behavior.inject(IS_DIR, injected(), key=str(tmp_path / "sub"))
    _, terminal = drain(connector.enumerate())
    assert isinstance(terminal, ConnectorError)
    errors.append(terminal)
    # 取得
    fs = ScriptedFsOps()
    connector = create_connector(tmp_path, fs)
    fs.behavior.inject(OPEN, injected(), key=str(tmp_path / "sub" / "a.md"))
    with pytest.raises(ConnectorError) as exc_info:
        connector.fetch(DocumentRef("sub/a.md", "sub/a.md"), 100)
    errors.append(exc_info.value)

    assert len(errors) == 5
    for error in errors:
        assert error.category is not ErrorCategory.CONNECTOR_INTERNAL_ERROR
        assert "EIO" in error.message
        assert error.__cause__ is None
        assert error.__suppress_context__ is True
        assert "SENTINEL" not in error.message
        assert "SENTINEL" not in logged_text(error)
        assert "forged line" not in logged_text(error)

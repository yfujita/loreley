"""`create` のルートの確認(FS 設計書 3.2・3.3。10章 #11)。"""

import errno
import os
import stat
from pathlib import Path

import pytest

from loreley_crawler.connectors.filesystem import (
    FileStat,
    FileSystemConnector,
    FileSystemConnectorType,
)
from loreley_crawler.connectors.interface import (
    ConnectorError,
    ErrorCategory,
    ErrorScope,
    RetryHint,
)
from tests.connectors.filesystem.support import (
    SOURCE_ID,
    create_connector,
    enumerate_ids,
    skip_if_root,
    write_file,
)
from tests.fakes.fake_fs_ops import (
    FILESYSTEM_ENCODING,
    REALPATH,
    SCANDIR,
    STAT,
    ScriptedFsOps,
)


def create_failure(connector_config: object, fs: ScriptedFsOps | None = None) -> ConnectorError:
    with pytest.raises(ConnectorError) as exc_info:
        FileSystemConnectorType(fs).create(SOURCE_ID, connector_config)
    return exc_info.value


def test_create_returns_a_connector_for_an_existing_directory(tmp_path: Path) -> None:
    connector = create_connector(tmp_path)

    assert isinstance(connector, FileSystemConnector)


def test_a_missing_root_is_source_not_found(tmp_path: Path) -> None:
    error = create_failure({"root": str(tmp_path / "missing")})

    assert error.category is ErrorCategory.SOURCE_NOT_FOUND
    assert error.scope is ErrorScope.SOURCE
    assert error.retry is RetryHint.PERMANENT
    assert "ENOENT" in error.message
    assert str(tmp_path / "missing") in error.message


def test_a_file_as_the_root_is_source_not_found(tmp_path: Path) -> None:
    file_path = write_file(tmp_path, "file.txt")

    error = create_failure({"root": str(file_path)})

    assert error.category is ErrorCategory.SOURCE_NOT_FOUND
    assert error.retry is RetryHint.PERMANENT


def test_a_root_that_stat_reports_as_a_regular_file_is_source_not_found(tmp_path: Path) -> None:
    # `scandir` が拒否しない状況でも、ディレクトリでないルートは受け付けない。
    fs = ScriptedFsOps()
    regular_file = FileStat(stat.S_IFREG | 0o644, 0, 0, 1, 1)
    fs.behavior.inject(STAT, regular_file, key=str(tmp_path))

    error = create_failure({"root": str(tmp_path)}, fs)

    assert error.category is ErrorCategory.SOURCE_NOT_FOUND
    assert "ディレクトリでない" in error.message


def test_a_root_below_a_file_is_source_not_found(tmp_path: Path) -> None:
    file_path = write_file(tmp_path, "file.txt")

    assert create_failure({"root": f"{file_path}/sub"}).category is ErrorCategory.SOURCE_NOT_FOUND


@skip_if_root
def test_an_unreadable_root_is_source_access_denied(tmp_path: Path) -> None:
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        error = create_failure({"root": str(locked)})
    finally:
        locked.chmod(0o755)

    assert error.category is ErrorCategory.SOURCE_ACCESS_DENIED
    assert error.scope is ErrorScope.SOURCE
    assert error.retry is RetryHint.PERMANENT
    assert "EACCES" in error.message


@pytest.mark.parametrize("operation", [STAT, SCANDIR])
def test_permission_errors_on_the_root_are_source_access_denied_without_real_permissions(
    tmp_path: Path, operation: str
) -> None:
    fs = ScriptedFsOps()
    fs.behavior.inject(operation, PermissionError(errno.EACCES, "denied"), key=str(tmp_path))

    error = create_failure({"root": str(tmp_path)}, fs)

    assert error.category is ErrorCategory.SOURCE_ACCESS_DENIED


def test_an_unreachable_share_is_a_transient_source_unreachable(tmp_path: Path) -> None:
    fs = ScriptedFsOps()
    fs.behavior.inject(STAT, OSError(errno.ESTALE, "stale"), key=str(tmp_path))

    error = create_failure({"root": str(tmp_path)}, fs)

    assert error.category is ErrorCategory.SOURCE_UNREACHABLE
    assert error.scope is ErrorScope.SOURCE
    assert error.retry is RetryHint.TRANSIENT
    assert "ESTALE" in error.message


def test_the_root_is_checked_by_stat_then_by_opening_and_closing_it(tmp_path: Path) -> None:
    fs = ScriptedFsOps()

    FileSystemConnectorType(fs).create(SOURCE_ID, {"root": str(tmp_path)})

    assert [(call.operation, call.key) for call in fs.behavior.calls_of(STAT, SCANDIR)] == [
        (STAT, str(tmp_path)),
        (SCANDIR, str(tmp_path)),
    ]


def test_a_root_that_is_a_symlink_to_a_directory_is_accepted(tmp_path: Path) -> None:
    write_file(tmp_path, "real/a.md")
    os.symlink(tmp_path / "real", tmp_path / "link")

    for follow in (False, True):
        connector = create_connector(tmp_path / "link", follow_symlinks=follow)
        assert enumerate_ids(connector) == {"a.md"}


def test_the_real_path_of_the_root_is_resolved_only_when_following_links(
    tmp_path: Path,
) -> None:
    fs = ScriptedFsOps()
    create_connector(tmp_path, fs)
    assert fs.behavior.calls_of(REALPATH) == []

    create_connector(tmp_path, fs, follow_symlinks=True)

    assert [call.key for call in fs.behavior.calls_of(REALPATH)] == [str(tmp_path)]


def test_a_filesystem_encoding_other_than_utf8_fails_the_creation(tmp_path: Path) -> None:
    fs = ScriptedFsOps()
    fs.behavior.inject(FILESYSTEM_ENCODING, "ascii")

    error = create_failure({"root": str(tmp_path)}, fs)

    assert error.category is ErrorCategory.CONNECTOR_INTERNAL_ERROR
    assert error.scope is ErrorScope.SOURCE
    assert error.retry is RetryHint.UNKNOWN
    assert "ascii" in error.message


@pytest.mark.parametrize("encoding", ["utf-8", "UTF-8", "utf8"])
def test_spellings_of_utf8_are_accepted(tmp_path: Path, encoding: str) -> None:
    fs = ScriptedFsOps()
    fs.behavior.inject(FILESYSTEM_ENCODING, encoding)

    assert create_connector(tmp_path, fs) is not None


def test_a_config_violation_is_reported_before_any_io(tmp_path: Path) -> None:
    fs = ScriptedFsOps()

    error = create_failure({"root": "relative"}, fs)

    assert error.category is ErrorCategory.CONFIG_INVALID
    assert fs.behavior.calls == []


def test_an_unclassified_os_error_on_the_root_is_raised_as_it_is(tmp_path: Path) -> None:
    fs = ScriptedFsOps()
    fs.behavior.inject(STAT, OSError(errno.ENOSPC, "no space"), key=str(tmp_path))

    with pytest.raises(OSError) as exc_info:
        FileSystemConnectorType(fs).create(SOURCE_ID, {"root": str(tmp_path)})

    assert not isinstance(exc_info.value, ConnectorError)
    assert exc_info.value.errno == errno.ENOSPC

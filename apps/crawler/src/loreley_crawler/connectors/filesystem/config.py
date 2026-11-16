"""`connector_config` の項目と検証(`validate_config`。FS 設計書 2章。案: CFS-P-1〜4)。

I/O をしない。違反は `config_invalid` の `ConnectorError`。説明文は固定文で、項目名(配列は添字)と
違反の種類だけを入れる(crawler-api がそのまま応答に載せるため、入力値は含めない)。
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass

from loreley_crawler.connectors.filesystem.patterns import (
    GlobPattern,
    compile_pattern,
    find_pattern_violation,
)
from loreley_crawler.connectors.filesystem.settings import FileSystemSettings
from loreley_crawler.connectors.interface import ConnectorError, ErrorCategory

ROOT = "root"
INCLUDE_PATTERNS = "include_patterns"
EXCLUDE_PATTERNS = "exclude_patterns"
FOLLOW_SYMLINKS = "follow_symlinks"
INCLUDE_HIDDEN = "include_hidden"

_KNOWN_ITEMS = frozenset(
    {ROOT, INCLUDE_PATTERNS, EXCLUDE_PATTERNS, FOLLOW_SYMLINKS, INCLUDE_HIDDEN}
)

# 既定の拡張子(Q2。確定。CFS-K-3)。固定の集合で、設定項目にしない(案。CFS-P-2)。
DEFAULT_EXTENSIONS = frozenset({".txt", ".md", ".markdown", ".html", ".htm", ".pdf"})


@dataclass(frozen=True)
class FileSystemConfig:
    """検証済みの設定。

    - `root`: 末尾の `/` を除いた絶対パス(`/` だけの場合を除く)
    - `include_patterns`: 既定の拡張子に**追加**で対象にするパターン(案。CFS-U-1)
    - `exclude_patterns`: 対象から除くパターン。ファイルにもディレクトリにも適用する
    """

    root: str
    include_patterns: tuple[GlobPattern, ...]
    exclude_patterns: tuple[GlobPattern, ...]
    follow_symlinks: bool
    include_hidden: bool

    @property
    def uses_patterns(self) -> bool:
        return bool(self.include_patterns or self.exclude_patterns)


def has_default_extension(file_name: str) -> bool:
    """最後の拡張子(名前の先頭だけの `.` は拡張子でない)を小文字にして照合する(CFS-P-4)。"""
    return os.path.splitext(file_name)[1].lower() in DEFAULT_EXTENSIONS


def parse_config(connector_config: object, settings: FileSystemSettings) -> FileSystemConfig:
    if not isinstance(connector_config, Mapping):
        raise _invalid("connector_config", "オブジェクトでない")
    for key in connector_config:
        if key not in _KNOWN_ITEMS:
            # 綴りの誤りを見逃さないための拒否。キー名は入力値なので説明文に含めない。
            raise _invalid("connector_config", "未知の項目がある")
    if ROOT not in connector_config:
        raise _invalid(ROOT, "必須の項目がない")
    return FileSystemConfig(
        root=_parse_root(connector_config[ROOT]),
        include_patterns=_parse_patterns(connector_config, INCLUDE_PATTERNS, settings),
        exclude_patterns=_parse_patterns(connector_config, EXCLUDE_PATTERNS, settings),
        follow_symlinks=_parse_flag(connector_config, FOLLOW_SYMLINKS),
        include_hidden=_parse_flag(connector_config, INCLUDE_HIDDEN),
    )


def _parse_root(value: object) -> str:
    if not isinstance(value, str):
        raise _invalid(ROOT, "文字列でない")
    if not value.startswith("/"):
        raise _invalid(ROOT, "`/` で始まる絶対パスでない")
    if "\0" in value:
        raise _invalid(ROOT, "NUL を含む")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise _invalid(ROOT, "孤立サロゲートを含む") from None
    if "//" in value:
        raise _invalid(ROOT, "連続する `/` を含む")
    # 末尾の `/` は除いて保持する(`/` だけの場合を除く)。
    root = value[:-1] if len(value) > 1 and value.endswith("/") else value
    if any(segment in {".", ".."} for segment in root.split("/")):
        raise _invalid(ROOT, "`.` または `..` のセグメントを含む")
    return root


def _parse_patterns(
    connector_config: Mapping[object, object], item: str, settings: FileSystemSettings
) -> tuple[GlobPattern, ...]:
    if item not in connector_config:
        return ()
    value = connector_config[item]
    if not isinstance(value, list):
        raise _invalid(item, "文字列の配列でない")
    if len(value) > settings.max_patterns:
        raise _invalid(item, f"{settings.max_patterns} 件を超えている")
    compiled = []
    for index, pattern in enumerate(value):
        if not isinstance(pattern, str):
            raise _invalid(f"{item}[{index}]", "文字列でない")
        violation = find_pattern_violation(pattern, max_bytes=settings.max_pattern_bytes)
        if violation is not None:
            raise _invalid(f"{item}[{index}]", violation)
        compiled.append(compile_pattern(pattern))
    return tuple(compiled)


def _parse_flag(connector_config: Mapping[object, object], item: str) -> bool:
    if item not in connector_config:
        return False
    value = connector_config[item]
    # `0`・`1`・文字列は拒否する。`bool` は `int` の派生なので、型を厳密に比べる。
    if type(value) is not bool:
        raise _invalid(item, "真偽値でない")
    return value


def _invalid(item: str, violation: str) -> ConnectorError:
    return ConnectorError.of(ErrorCategory.CONFIG_INVALID, f"{item}: {violation}")

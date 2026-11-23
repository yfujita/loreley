"""ログの呼び出しに、値や例外を持ち込む引数を渡さないこと(A 5.5。module R11)。

ログに出してよいのは、固定文とクラス名・送出元の位置などだけ。`extra`・`stack_info`・`exc_info`
(と、`exc_info` を暗黙に付ける `.exception(...)`)は、値・例外のメッセージ・スタックを
ログに持ち込めるので、ログの呼び出しでは使わない。

検査の対象はログのメソッドの呼び出しだけで、ログと無関係の `extra`(pydantic の
`ConfigDict(extra="forbid")` など)は対象にしない。
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "loreley_api"
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "critical", "exception", "log", "fatal"}
FORBIDDEN_KEYWORDS = {"extra", "stack_info", "exc_info"}


def log_method_calls_in(tree: ast.AST) -> list[ast.Call]:
    """ログのメソッド(`.info(...)` など)の呼び出し。受け手(ロガーの変数名)は問わない。

    ロガーの変数名を決め打ちにしない(`_log` のような別名や `self._logger` で、検査から外れない)。
    """
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in LOG_METHODS
    ]


def forbidden_logging_calls_in(tree: ast.AST) -> list[int]:
    """禁止された呼び出しの行番号。

    対象は、ログのメソッドへの `extra`・`stack_info`・`exc_info` の指定と、
    `.exception(...)` の呼び出しだけ。
    """
    lines = []
    for call in log_method_calls_in(tree):
        keywords = {keyword.arg for keyword in call.keywords}
        is_exception_call = call.func.attr == "exception"
        if is_exception_call or FORBIDDEN_KEYWORDS & keywords:
            lines.append(call.lineno)
    return lines


def source_trees() -> Iterator[tuple[str, ast.AST]]:
    for path in SOURCE_ROOT.rglob("*.py"):
        yield str(path.relative_to(SOURCE_ROOT)), ast.parse(path.read_text(encoding="utf-8"))


# --- 検査器の自己テスト(空振りしないこと) ---


def test_the_detector_finds_log_method_calls_whatever_the_logger_is_called() -> None:
    tree = ast.parse(
        "_log.info('a')\n"
        "other.warning('b')\n"
        "self._logger.log(20, 'c')\n"
        "logging.getLogger('x').error('d')\n"
        "unrelated.append('e')\n"
    )

    assert [call.lineno for call in log_method_calls_in(tree)] == [1, 2, 3, 4]


@pytest.mark.parametrize(
    "statement",
    [
        "logger.error('x', exc_info=True)",
        "logger.info('x', extra={'v': 1})",
        "logger.warning('x', stack_info=True)",
        "logger.exception('x')",
        "anything.exception('x')",
        "logging.getLogger('x').error('x', exc_info=error)",
        "self._logger.log(20, 'x', extra={'v': 1})",
    ],
)
def test_the_detector_finds_a_forbidden_call_whatever_the_logger_is_called(statement: str) -> None:
    assert forbidden_logging_calls_in(ast.parse(statement)) == [1]


@pytest.mark.parametrize(
    "statement",
    [
        "ConfigDict(extra='forbid')",
        "foo(extra=1)",
        "model_config = {'extra': 'forbid'}",
        "settings.build(extra='x', exc_info=1)",
        "logger.info('x %s', value)",
        "logger.error('x: error=%s', type(error).__name__)",
    ],
)
def test_the_detector_ignores_what_has_nothing_to_do_with_logging(statement: str) -> None:
    assert forbidden_logging_calls_in(ast.parse(statement)) == []


# --- 実ソースの検査 ---


def test_the_logging_calls_in_the_source_are_found() -> None:
    """検査が空振りしていない(access_logger・logger の呼び出しが見つかる)。"""
    found = sum(len(log_method_calls_in(tree)) for _, tree in source_trees())

    assert found >= 2


def test_no_logging_call_passes_extra_stack_info_or_exc_info_or_uses_exception() -> None:
    offenders = [
        f"{location}:{line}"
        for location, tree in source_trees()
        for line in forbidden_logging_calls_in(tree)
    ]

    assert offenders == []

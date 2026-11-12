import io
import logging

import pytest

from loreley_indexer.common.log_masking import (
    REDACTED,
    UNFORMATTABLE_MESSAGE,
    SecretRedactionFilter,
    redact_url_credentials,
)


@pytest.fixture
def log_output() -> io.StringIO:
    return io.StringIO()


def make_logger(secrets: list[str], output: io.StringIO) -> logging.Logger:
    logger = logging.getLogger(f"test.log_masking.{id(output)}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.StreamHandler(output)
    handler.addFilter(SecretRedactionFilter(secrets))
    logger.addHandler(handler)
    return logger


def test_secret_in_message_is_redacted(log_output: io.StringIO) -> None:
    logger = make_logger(["hunter2"], log_output)
    logger.info("connecting with password hunter2")
    assert log_output.getvalue() == f"connecting with password {REDACTED}\n"


def test_secret_in_formatted_args_is_redacted(log_output: io.StringIO) -> None:
    logger = make_logger(["hunter2"], log_output)
    logger.info("password=%s", "hunter2")
    assert log_output.getvalue() == f"password={REDACTED}\n"


def test_secret_in_exception_traceback_is_redacted(log_output: io.StringIO) -> None:
    logger = make_logger(["hunter2"], log_output)
    try:
        raise RuntimeError("bad password hunter2")
    except RuntimeError:
        logger.exception("failed")
    assert "hunter2" not in log_output.getvalue()
    assert "RuntimeError" in log_output.getvalue()


def test_longer_secret_is_redacted_whole_even_if_it_contains_a_shorter_secret(
    log_output: io.StringIO,
) -> None:
    logger = make_logger(["abc", "abcdef"], log_output)
    logger.info("token abcdef")
    assert log_output.getvalue() == f"token {REDACTED}\n"


def test_empty_secret_is_ignored(log_output: io.StringIO) -> None:
    logger = make_logger([""], log_output)
    logger.info("hello")
    assert log_output.getvalue() == "hello\n"


@pytest.mark.parametrize(
    ("message", "args", "error_class"),
    [
        ("expects two values: %s %s", ("hunter2",), "TypeError"),  # 引数が足りない
        ("bad directive: %d", ("hunter2",), "TypeError"),  # 型が合わない
        ("bad format: %(name)s", ({"other": "hunter2"},), "KeyError"),  # 辞書にキーがない
        ("unsupported: %y", ("hunter2",), "ValueError"),  # 不正な書式指定
    ],
)
def test_message_that_cannot_be_formatted_does_not_raise_and_does_not_leak_args(
    log_output: io.StringIO, message: str, args: tuple[object, ...], error_class: str
) -> None:
    record = logging.LogRecord("app.worker", logging.INFO, __file__, 1, message, args, None)

    assert SecretRedactionFilter(["hunter2"]).filter(record) is True

    handler = logging.StreamHandler(log_output)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.handle(record)
    assert (
        log_output.getvalue()
        == f"{UNFORMATTABLE_MESSAGE} (logger=app.worker, error={error_class})\n"
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://user:pass@opensearch:9200", f"http://{REDACTED}@opensearch:9200"),
        ("https://user@host/path?q=1", f"https://{REDACTED}@host/path?q=1"),
        ("http://opensearch:9200", "http://opensearch:9200"),
        ("http://user:pass@[::1]:9200", f"http://{REDACTED}@[::1]:9200"),
        ("http://user:pass@opensearch", f"http://{REDACTED}@opensearch"),
        ("http://user:pass@opensearch:0", f"http://{REDACTED}@opensearch:0"),
        # 不正なポートでも例外にせず、認証情報は伏せる(ポートは表示から落とす)。
        ("http://user:pass@opensearch:99999", f"http://{REDACTED}@opensearch"),
        ("http://user:pass@opensearch:abc/path", f"http://{REDACTED}@opensearch/path"),
    ],
)
def test_redact_url_credentials(url: str, expected: str) -> None:
    assert redact_url_credentials(url) == expected

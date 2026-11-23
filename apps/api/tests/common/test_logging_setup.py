import io
import logging

import pytest

from loreley_api.common.logging_setup import (
    LOG_FORMAT,
    RESTRICTED_LOG_LEVEL,
    RESTRICTED_LOGGER_NAMES,
    configure_logging,
)

pytestmark = pytest.mark.usefixtures("restore_logging")


def test_the_root_level_follows_the_argument_and_handlers_are_replaced() -> None:
    first, second = io.StringIO(), io.StringIO()
    configure_logging(level="INFO", stream=first)
    configure_logging(level="WARNING", stream=second)

    logging.getLogger("app").info("hidden")
    logging.getLogger("app").warning("shown")

    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert "shown" in second.getvalue()
    assert first.getvalue() == ""


def test_the_output_has_the_time_the_level_the_logger_name_and_the_message() -> None:
    stream = io.StringIO()
    configure_logging(level="INFO", stream=stream)

    logging.getLogger("app.sub").info("hello")

    assert LOG_FORMAT == "%(asctime)s %(levelname)s %(name)s %(message)s"
    line = stream.getvalue().rstrip("\n")
    assert line.endswith(" INFO app.sub hello")


def test_the_returned_handler_is_the_one_installed() -> None:
    handler = configure_logging(level="INFO", stream=io.StringIO())

    assert logging.getLogger().handlers == [handler]


def test_uvicorn_access_is_held_at_error_even_with_debug() -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)

    logger = logging.getLogger("uvicorn.access")
    logger.info('127.0.0.1 - "GET /SENTINEL-PATH HTTP/1.1" 200')
    logger.warning("SENTINEL-WARNING")
    logger.error("POSITIVE-CONTROL")

    assert "uvicorn.access" in RESTRICTED_LOGGER_NAMES
    assert logger.level == RESTRICTED_LOG_LEVEL
    assert "SENTINEL" not in stream.getvalue()
    assert "POSITIVE-CONTROL" in stream.getvalue()


def test_the_restricted_loggers_are_the_documented_ones() -> None:
    """C 8.5: OpenSearch・urllib3 は、ID を含む URL・本文を出すので ERROR 以上に固定する。"""
    assert set(RESTRICTED_LOGGER_NAMES) == {
        "uvicorn.access",
        "opensearch",
        "opensearchpy",
        "opensearchpy.trace",
        "opensearchpy.helpers",
        "urllib3",
    }


@pytest.mark.parametrize("name", RESTRICTED_LOGGER_NAMES)
def test_every_restricted_logger_is_held_at_error_even_with_debug(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)

    logger = logging.getLogger(name)
    # opensearch-py は、import した時点で `opensearchpy.trace` の `propagate` を False にする
    # (トレース用のロガー)。import の順序でこのテストの結果が変わらないよう、そろえる。
    monkeypatch.setattr(logger, "propagate", True)
    logger.debug("SENTINEL-DEBUG GET /SENTINEL-ID")
    logger.info("SENTINEL-INFO")
    logger.warning("SENTINEL-WARNING")
    logger.error("POSITIVE-CONTROL")

    assert logger.level == RESTRICTED_LOG_LEVEL
    assert "SENTINEL" not in stream.getvalue()
    assert "POSITIVE-CONTROL" in stream.getvalue()


def test_a_child_of_a_restricted_logger_is_restricted_too() -> None:
    """`urllib3.connectionpool` などの子のロガーは、親の水準を引き継ぐ。"""
    stream = io.StringIO()
    configure_logging(level="DEBUG", stream=stream)

    logging.getLogger("urllib3.connectionpool").debug("SENTINEL-DEBUG")
    logging.getLogger("opensearch.client").info("SENTINEL-INFO")

    assert stream.getvalue() == ""

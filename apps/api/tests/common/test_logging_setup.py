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

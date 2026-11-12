import io
import logging
import re
from pathlib import Path

import opensearchpy
import pytest
import urllib3.connectionpool
from opensearchpy import client as opensearch_client
from opensearchpy import connection_pool, helpers
from opensearchpy.connection import base as opensearch_connection

from loreley_indexer.common.log_setup import (
    RESTRICTED_LOG_LEVEL,
    RESTRICTED_LOGGER_NAMES,
    configure_logging,
)

pytestmark = pytest.mark.usefixtures("restore_logging")


def test_secrets_are_redacted_in_the_output_including_tracebacks() -> None:
    stream = io.StringIO()
    configure_logging(level="DEBUG", secrets=["SENTINEL-PASSWORD"], stream=stream)

    logging.getLogger("app").info("connecting with %s", "SENTINEL-PASSWORD")
    try:
        raise RuntimeError("failed with SENTINEL-PASSWORD")
    except RuntimeError:
        logging.getLogger("app").exception("failed")

    assert "SENTINEL-PASSWORD" not in stream.getvalue()
    assert "***" in stream.getvalue()


# --- ライブラリのロガー(R9) ---


def library_logger_names_in_the_source() -> set[str]:
    """インストール済みの opensearch-py のソースが `getLogger("...")` で使う名前すべて。"""
    package_dir = Path(opensearchpy.__file__).parent
    pattern = re.compile(r"""getLogger\(\s*["']([^"']+)["']\s*\)""")
    return {
        name
        for path in package_dir.rglob("*.py")
        for name in pattern.findall(path.read_text(encoding="utf-8"))
    }


def test_the_restricted_names_match_the_loggers_the_installed_library_really_uses() -> None:
    """名前が食い違うと、制限が効かないまま黙って漏れる(例: `opensearch.trace` は実在しない)。"""
    real_loggers = {
        opensearch_connection.logger,
        opensearch_connection.tracer,
        connection_pool.logger,
        opensearch_client.logger,
        helpers.actions.logger,
    }

    assert {logger.name for logger in real_loggers} == {
        "opensearch",
        "opensearchpy.trace",
        "opensearchpy.helpers",
    }
    assert {logger.name for logger in real_loggers} <= set(RESTRICTED_LOGGER_NAMES)
    assert "urllib3" in RESTRICTED_LOGGER_NAMES
    assert library_logger_names_in_the_source() >= {"opensearch", "opensearchpy.trace"}


def test_every_logger_name_the_library_uses_is_held_at_the_restricted_level() -> None:
    configure_logging(level="DEBUG", secrets=[], stream=io.StringIO())

    for name in library_logger_names_in_the_source():
        effective_level = logging.getLogger(name).getEffectiveLevel()
        assert effective_level >= RESTRICTED_LOG_LEVEL, name
    assert urllib3.connectionpool.log.getEffectiveLevel() >= RESTRICTED_LOG_LEVEL


# `opensearchpy.trace` は含めない。ライブラリが `propagate=False` にするので、制限がなくても
# ルートのハンドラには届かず、この検査では何も確かめられない(水準は上のテストが確かめる)。
@pytest.mark.parametrize(
    "logger_name", ["opensearch", "opensearchpy.helpers", "opensearchpy.x.y", "urllib3"]
)
def test_the_libraries_never_emit_below_error_even_with_debug(logger_name: str) -> None:
    """失敗の WARNING(ID を含む URL)・成功の INFO・DEBUG の本文は、どれも出ない。ERROR は出す。"""
    stream = io.StringIO()
    configure_logging(level="DEBUG", secrets=[], stream=stream)

    logger = logging.getLogger(logger_name)
    logger.debug("body=SENTINEL-BODY")
    logger.info("url=SENTINEL-URL")
    logger.warning("GET /index/_doc/SENTINEL-ID [status:404]")
    logger.error("failed kind=POSITIVE-CONTROL")

    assert stream.getvalue().count("SENTINEL") == 0
    assert "POSITIVE-CONTROL" in stream.getvalue()


def test_the_trace_logger_is_not_a_child_of_the_opensearch_logger() -> None:
    """`opensearch` だけを制限しても、トレース用のロガーは止まらない(名前の階層が別)。"""
    assert not opensearch_connection.tracer.name.startswith("opensearch.")


def test_the_root_level_follows_the_argument_and_handlers_are_replaced() -> None:
    first, second = io.StringIO(), io.StringIO()
    configure_logging(level="INFO", secrets=[], stream=first)
    configure_logging(level="WARNING", secrets=[], stream=second)

    root = logging.getLogger()
    logging.getLogger("app").info("hidden")
    logging.getLogger("app").warning("shown")

    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    assert "shown" in second.getvalue()
    assert first.getvalue() == ""

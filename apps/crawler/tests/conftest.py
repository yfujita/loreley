import logging
from collections.abc import Iterator

import pytest

from loreley_crawler.common.log_setup import RESTRICTED_LOGGER_NAMES
from tests.fakes.clock import FixedClock


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """ルートと制限対象ロガーの設定を戻す(`configure_logging` を呼ぶテストの後始末)。"""
    names = ["", *RESTRICTED_LOGGER_NAMES]
    saved = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).level) for name in names
    }
    yield
    for name, (handlers, level) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)

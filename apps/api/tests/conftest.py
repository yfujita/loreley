import logging
import socket
from collections.abc import Iterator

import pytest

from loreley_api.common.logging_setup import RESTRICTED_LOGGER_NAMES
from tests.fakes.clock import FixedClock
from tests.fakes.inline_runner import InlineRunner


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


@pytest.fixture
def fixed_clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def inline_runner() -> InlineRunner:
    return InlineRunner()


@pytest.fixture
def unresolvable_invalid_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.invalid` のホストの名前解決を、実 DNS に問い合わせず失敗させる(それ以外は実物に任せる)。

    実 DNS は、応答しない環境で遅くなる。ローカルのスタブ(`127.0.0.1`)への接続は妨げない。
    """
    real_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
        if isinstance(host, str) and host.endswith(".invalid"):
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return real_getaddrinfo(host, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

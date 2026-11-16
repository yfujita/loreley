import os

import pytest

PREFIX = "LORELEY_CRAWLER_"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """他の環境の `LORELEY_CRAWLER_*` に左右されない。"""
    for name in list(os.environ):
        if name.startswith(PREFIX):
            monkeypatch.delenv(name)

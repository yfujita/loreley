import pytest

from tests.api.support import ApiEnv, make_api_env


@pytest.fixture
def api() -> ApiEnv:
    return make_api_env()

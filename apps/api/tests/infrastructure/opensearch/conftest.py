import pytest

from loreley_api.infrastructure.opensearch import IndexNames, ReadOnlyOpenSearch
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient

INDEX_NAMES = IndexNames(
    sources="test-sources",
    jobs="test-jobs",
    deletions="test-deletions",
    search="test-search-alias",
)


@pytest.fixture
def fake_client() -> FakeOpenSearchClient:
    return FakeOpenSearchClient()


@pytest.fixture
def readonly(fake_client: FakeOpenSearchClient) -> ReadOnlyOpenSearch:
    return ReadOnlyOpenSearch(fake_client)

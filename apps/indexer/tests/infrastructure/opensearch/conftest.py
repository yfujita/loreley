from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch


@pytest.fixture
def transport() -> MagicMock:
    return MagicMock()


@pytest.fixture
def real_client(transport: MagicMock) -> OpenSearch:
    """実際の `OpenSearch` クライアント。通信層(transport)だけをモックに差し替える。

    クライアントのメソッドが組み立てる (method, url, params) まで確認でき、ネットワーク接続は不要。
    """
    client = OpenSearch(hosts=["http://opensearch.invalid:9200"])
    client.transport = transport
    return client

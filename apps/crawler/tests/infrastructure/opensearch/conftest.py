from unittest.mock import MagicMock

import pytest
from opensearchpy import OpenSearch
from opensearchpy.serializer import JSONSerializer


@pytest.fixture
def transport() -> MagicMock:
    mock = MagicMock()
    mock.serializer = JSONSerializer()  # `bulk` が本文の組み立てに使う
    return mock


@pytest.fixture
def real_client(transport: MagicMock) -> OpenSearch:
    """実際の `OpenSearch` クライアント。通信層(transport)だけをモックに差し替える。

    クライアントのメソッドが組み立てる (method, url, params, body) まで確認でき、ネットワーク接続は
    不要。
    """
    client = OpenSearch(hosts=["http://opensearch.invalid:9200"])
    client.transport = transport
    return client

"""urllib3 の例外の分類(接続前の失敗 / 送信後の応答喪失。B 9.1。C 4.3。D 4.9)。

urllib3 2.x の継承(`NameResolutionError` は `NewConnectionError` の子、`NewConnectionError` は
`ConnectTimeoutError` の子)に合わせ、**狭いほうから順に**判定する。接続を使い回さない(C 4.1)ので、
`before_send` の 4 つは確実に「送る前」の失敗になる。

`SSLError` は接続の確立中の失敗として `before_send` にする。MVP は `CRAWLER_URL` が `http` 限定
(C 7.3)なので通常は起きない。`https` を許す将来は、送った後の TLS の失敗も同じ型になりうるので、
分類を見直すこと(C 4.3)。

`str(error)` は URL・ホスト名を含みうるので、返り値にもログにも載せない(R11)。
"""

from urllib3.exceptions import (
    ConnectTimeoutError,
    HTTPError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
    SSLError,
)

from loreley_api.infrastructure.crawler_client.client import CrawlerTransportFailed


def classify_transport_failure(error: HTTPError) -> CrawlerTransportFailed:
    if isinstance(error, NameResolutionError):
        return CrawlerTransportFailed("before_send", "name_resolution")
    if isinstance(error, NewConnectionError):
        # 接続拒否・到達不能。Crawler の起動時の回復中(受付の開始前)もここに見える(B 9.1)。
        return CrawlerTransportFailed("before_send", "connection_failed")
    if isinstance(error, ConnectTimeoutError):
        return CrawlerTransportFailed("before_send", "connect_timeout")
    if isinstance(error, SSLError):
        return CrawlerTransportFailed("before_send", "tls_failure")
    if isinstance(error, ReadTimeoutError):
        return CrawlerTransportFailed("after_send", "response_timeout")
    if isinstance(error, ProtocolError):
        return CrawlerTransportFailed("after_send", "connection_lost")
    # その他の urllib3 の例外(デコードの失敗など)は、送った可能性があるので安全側(結果不明)にする。
    return CrawlerTransportFailed("after_send", "http_error")

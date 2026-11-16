"""複数のモジュールが共有するエラー型(module 4.11)。

メッセージ・`reason`・`error_type` は固定の短い文字列で、本文・認証情報・識別子を入れない(R11)。
Indexer の異常(500・503・接続エラー・タイムアウトなど)は、例外ではなく `indexer_client` の
型付きの結果(`IndexerUnavailable`・`IndexerRejected`)で返すので、ここには置かない。
"""


class CrawlerError(Exception):
    """Crawler が意図して送出する例外の基底。"""


class StoreUnavailableError(CrawlerError):
    """Store 層(OpenSearch)全体の異常。接続できない・タイムアウト・クラスタの異常など。

    記録ごとの結果(競合・存在しない・すでに存在する)とは別で、個別には処理せず伝播させる。
    呼び出し側は、リトライを尽くしたら `store_unavailable` で扱う(architecture 4.8)。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class StoreUnexpectedResponseError(CrawlerError):
    """Store 層の想定外の応答。クエリやマッピングの誤りなど、リトライで直らない異常。

    Crawler 側の不具合の疑いなので、呼び出し側は個別に処理せず伝播させる(最後の手段の
    `failed`(`internal_error`)になる)。`error_type` は OpenSearch のエラー種別名か
    `http_{status}` だけ(`reason` などの本文は含まない)。
    """

    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.error_type = error_type


def is_store_unavailable(error: Exception) -> bool:
    """`run_with_retry` の `is_retryable_error` に渡す。Store 層全体の異常だけリトライする。

    `StoreUnexpectedResponseError` はリトライしても直らない(Crawler の不具合の疑い)ので含めない。
    """
    return isinstance(error, StoreUnavailableError)

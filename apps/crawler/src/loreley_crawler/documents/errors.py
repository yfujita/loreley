"""`documents` 固有のエラー。"""

from loreley_crawler.common.errors import CrawlerError


class EnumerationTooLargeError(CrawlerError):
    """列挙した文書数が `max_enumerated_documents` を超えた(`enumeration_too_large`)。

    重複除去・衝突検出の ID 集合を保持できない規模。呼び出し側(`crawl`)はジョブを `failed` にする
    (architecture 7.7。CA-P-26)。Connector の分類(interface 6.2)にはない、共通処理の失敗。
    """

    def __init__(self, max_enumerated_documents: int) -> None:
        super().__init__(f"enumerated documents exceed the limit of {max_enumerated_documents}")
        self.max_enumerated_documents = max_enumerated_documents

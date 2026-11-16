"""`Connector`・`ConnectorType` の偽物(テスト用)。列挙・取得・失敗・`close` の記録を制御できる。

- 列挙は台本(`items`)で決める。`DocumentRef` を返し、`Completed` で完了し、例外の項目は送出する
  (列挙の `Failed`)。台本が尽きた後の `next()` は `AssertionError`(終端のない台本のテスト用の
  誤りを、完了と取り違えない)。`enumerate()` のたびに、同じ台本を最初から返す。
- 取得は `documents`(`locator` → `FetchedDocument`)で決める。`max_bytes` を超える原本は
  `oversize` にする。一時的な失敗などは `behavior.inject(FETCH, error, key=str(locator))`。
- `FakeBehavior` の操作名: `NEXT`・`FETCH`・`CONNECTOR_CLOSE`・`STREAM_CLOSE`・
  `VALIDATE_CONFIG`・`CREATE`。
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from loreley_crawler.connectors.interface import (
    Completed,
    Connector,
    ConnectorError,
    ConnectorType,
    DocumentMetadata,
    DocumentRef,
    EnumerationStream,
    ErrorCategory,
    FetchedDocument,
)
from tests.fakes.behavior import FakeBehavior

NEXT = "next"
FETCH = "fetch"
CONNECTOR_CLOSE = "connector_close"
STREAM_CLOSE = "stream_close"
VALIDATE_CONFIG = "validate_config"
CREATE = "create"

StreamItem = DocumentRef | Completed | BaseException

FIXED_MODIFIED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def fetched_document(
    content: bytes, *, title: str = "title", mime_type: str = "text/plain"
) -> FetchedDocument:
    return FetchedDocument(
        content, DocumentMetadata(title, mime_type, FIXED_MODIFIED_AT, path=title, url=None)
    )


class FakeEnumerationStream(EnumerationStream):
    """終端(`Completed` か例外)に達した後の `next()` は、同じ終端を繰り返す(実装の契約)。"""

    def __init__(self, connector: "FakeConnector") -> None:
        self._connector = connector
        self._items = list(connector.items)
        self._terminal: Completed | BaseException | None = None
        self.closed = False

    def next(self) -> DocumentRef | Completed:
        if self.closed:
            raise RuntimeError("enumeration stream is closed")
        outcome = self._connector.behavior.enter(NEXT)
        if outcome is not None:
            return outcome.value
        if self._terminal is None:
            self._terminal = self._advance()
            if isinstance(self._terminal, DocumentRef):
                item, self._terminal = self._terminal, None
                return item
        if isinstance(self._terminal, BaseException):
            raise self._terminal
        return self._terminal

    def close(self) -> None:
        self._connector.behavior.enter(STREAM_CLOSE)
        self.closed = True

    def _advance(self) -> DocumentRef | Completed | BaseException:
        if not self._items:
            raise AssertionError("the scripted enumeration has no terminal item")
        return self._items.pop(0)


class FakeConnector(Connector):
    def __init__(
        self,
        items: Sequence[StreamItem] = (),
        documents: Mapping[object, FetchedDocument] | None = None,
    ) -> None:
        self.items = tuple(items)
        self.documents = dict(documents or {})
        self.behavior = FakeBehavior()
        self.streams: list[FakeEnumerationStream] = []
        self.fetch_calls: list[tuple[DocumentRef, int]] = []
        self.close_count = 0

    @classmethod
    def of(cls, files: Mapping[str, bytes], *, then: StreamItem | None = None) -> "FakeConnector":
        """名前を `external_id` と `locator` にして辞書の順に列挙し、`then`(既定は完了)で終える。"""
        refs = [DocumentRef(external_id=name, locator=name) for name in files]
        documents = {name: fetched_document(content, title=name) for name, content in files.items()}
        return cls([*refs, Completed() if then is None else then], documents)

    def enumerate(self) -> EnumerationStream:
        stream = FakeEnumerationStream(self)
        self.streams.append(stream)
        return stream

    def fetch(self, ref: DocumentRef, max_bytes: int) -> FetchedDocument:
        self.fetch_calls.append((ref, max_bytes))
        outcome = self.behavior.enter(FETCH, str(ref.locator))
        if outcome is not None:
            return outcome.value
        fetched = self.documents.get(ref.locator)
        if fetched is None:
            raise ConnectorError.of(ErrorCategory.FETCH_NOT_FOUND, "no such document")
        if len(fetched.content) > max_bytes:
            raise ConnectorError.of(ErrorCategory.OVERSIZE, "too large")
        return fetched

    def close(self) -> None:
        self.behavior.enter(CONNECTOR_CLOSE)
        self.close_count += 1


class FakeConnectorType(ConnectorType):
    def __init__(self, connector: Connector | None = None) -> None:
        self.connector = connector if connector is not None else FakeConnector()
        self.behavior = FakeBehavior()
        self.validated_configs: list[object] = []
        self.created: list[tuple[str, object]] = []

    def validate_config(self, connector_config: object) -> None:
        self.validated_configs.append(connector_config)
        self.behavior.enter(VALIDATE_CONFIG)

    def create(self, source_id: str, connector_config: object) -> Connector:
        self.created.append((source_id, connector_config))
        self.behavior.enter(CREATE)
        return self.connector

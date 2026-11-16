"""Connector が返す値(interface 3.2・4章)。いずれも変更できない。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DocumentRef:
    """列挙が返す 1 件分の参照。

    - `external_id`: 規則適用前の値(interface 5.1)。規則の適用は `documents` が行う
    - `locator`: Connector が `fetch` で文書を再解決するための値。本体は中身を見ない
    - `size_hint`: 取得前に分かる原本のバイト数(任意)
    """

    external_id: str
    locator: object
    size_hint: int | None = None


@dataclass(frozen=True)
class DocumentMetadata:
    """文書のメタデータ(interface 4章)。`size`・`content_hash` は共通処理が導出するので持たない。"""

    title: str
    mime_type: str
    source_updated_at: datetime
    path: str | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        # オフセットなしの日時は、Indexer がバッチ全体を 400 にする(K59)。
        if self.source_updated_at.utcoffset() is None:
            raise ValueError("source_updated_at must include a timezone offset")


@dataclass(frozen=True)
class FetchedDocument:
    """取得の結果。`content` は原本の全体(MVP は参照ではなく原本そのものを渡す)。"""

    content: bytes
    metadata: DocumentMetadata


@dataclass(frozen=True)
class Completed:
    """列挙の完了の目印。`next()` が返す。

    Python の反復の終わり(`StopIteration`)を完了に使わない。終端なしで途切れた列挙を、完了と
    区別するため(interface 3.3 の 1)。
    """

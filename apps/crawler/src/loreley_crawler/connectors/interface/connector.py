"""Connector の抽象(interface 3.2)。

呼び出しの規則:
- 同じ `Connector` への呼び出し(`close` を含む)は、Job Runner のスレッドだけが直列に行う
  (module R9)。並行呼び出しへの対応は要らない。
- Connector は内部でリトライしない(CI-P-5)。失敗は `ConnectorError` で表す。
"""

from abc import ABC, abstractmethod

from loreley_crawler.connectors.interface.models import Completed, DocumentRef, FetchedDocument


class EnumerationStream(ABC):
    """列挙。0 件以上の `DocumentRef` のあと、必ず `Completed` か `ConnectorError` で終わる。

    終端なしで途切れた列挙(`close` された、プロセスが終了した)は完了とみなさない。
    """

    @abstractmethod
    def next(self) -> DocumentRef | Completed:
        """次の 1 件か、完了の目印を返す。列挙の失敗(Failed)は `ConnectorError` の送出で表す。"""

    @abstractmethod
    def close(self) -> None:
        """列挙だけを打ち切る。`Connector` は `fetch` に使い続けられる。"""


class Connector(ABC):
    """データソースの列挙と取得。`ConnectorType.create` が作る。"""

    @abstractmethod
    def enumerate(self) -> EnumerationStream:
        """列挙を始める。失敗は返された `EnumerationStream.next` が送出する。"""

    @abstractmethod
    def fetch(self, ref: DocumentRef, max_bytes: int) -> FetchedDocument:
        """文書の原本とメタデータを得る。何度でも呼べる(呼ぶたびに読み直す)。

        原本が `max_bytes` を超えるときは、全体を読み込まずに `oversize` を送出する。
        """

    @abstractmethod
    def close(self) -> None:
        """保持している接続・ハンドルなどを解放する。"""


class ConnectorType(ABC):
    """`connector_type` ごとに 1 つ。設定の検証と `Connector` の生成。"""

    @abstractmethod
    def validate_config(self, connector_config: object) -> None:
        """設定の構文・型・値域・項目間の整合を確認する。I/O をしない。

        違反は `config_invalid` の `ConnectorError`。`connector_config` は JSON から得た値で、
        オブジェクトとは限らない(型の違反も検出すること)。
        """

    @abstractmethod
    def create(self, source_id: str, connector_config: object) -> Connector:
        """`Connector` を作る。接続を伴う確認(FS ではルートの確認)の失敗は `ConnectorError`。"""

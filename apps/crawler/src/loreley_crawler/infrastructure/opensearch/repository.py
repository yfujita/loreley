"""Store 層の Repository インターフェース(module 4.8。architecture 3.1。CM-K-4)。

OpenSearch を KVS のように使い、索引ごとに 1 インスタンスが、記録を ID で読み書きする。
記録の形式と業務上の判断は持たない(`sources`・`jobs` が持つ)。操作は次のとおり。
- 取得(版つき)、`create`(存在しない場合だけ成功)、版条件つきの置き換え、版条件つきの削除
- 単純な条件での一覧(並べ替え・件数上限)
- 全件走査(PIT + `search_after`。ページ単位の反復)
- ID のバルク削除

条件指定の削除(`delete_by_query` に相当)は置かない。ソース削除の順 3(architecture 8.1)は、
`record_type` ごとの全件走査 + ID のバルク削除で行う(結果は同じで、契約が単純になる)。
無条件の書き込み(版も `create` も使わない置き換え・削除)も置かない。

**タイムアウト・接続断の後のリトライで返る `AlreadyExists`・`Conflict` の扱い**: 書き込みの
応答が失われた(タイムアウト・接続断で `StoreUnavailableError` になった)後に、同じ書き込みを
リトライすると、最初の書き込みがすでに成功していたために `AlreadyExists`(`create`)や
`Conflict`(版条件つきの置き換え・削除)が返ることがある。これは「他者に取られた・書き換えられた」
とは限らない。呼び出し側は、これらを受けたら記録を読み直し、所有者(`owner`・`job_id` など、
自分が書いた内容)を確認してから判断すること(自分が書いた内容なら、成功として扱う)。

`Repository` を実装するもの: `OpenSearchRepository`(本番)と、テスト用のメモリ上の実装
(`tests/fakes/in_memory_repository.py`)。両方が同じ契約(同じ結果区分)に従う。
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any

from loreley_crawler.infrastructure.opensearch.queries import RecordFilter, SortKey
from loreley_crawler.infrastructure.opensearch.results import (
    BulkDeleteResult,
    CreateOutcome,
    DeleteOutcome,
    ReplaceOutcome,
    StoredRecord,
)

# OpenSearch の `max_result_window` の既定値。通常の検索が返せる先頭からの件数の上限。
LIST_MAX_SIZE = 10_000

RecordPages = Iterator[list[StoredRecord]]


class Repository(ABC):
    @abstractmethod
    def fetch(self, record_id: str) -> StoredRecord | None:
        """ID で取得する(版つき)。ない場合は None。"""

    @abstractmethod
    def create(self, record_id: str, body: Mapping[str, Any]) -> CreateOutcome:
        """記録が存在しない場合だけ作る。すでにあれば `AlreadyExists` で、書き換えない。"""

    @abstractmethod
    def replace_if_unchanged(
        self, record_id: str, body: Mapping[str, Any], *, seq_no: int, primary_term: int
    ) -> ReplaceOutcome:
        """読んだ版を条件にした置き換え。版が合わなければ `Conflict`(`NotFound`)で、書かない。"""

    @abstractmethod
    def delete_if_unchanged(
        self, record_id: str, *, seq_no: int, primary_term: int
    ) -> DeleteOutcome:
        """読んだ版を条件にした削除。版が合わなければ `Conflict`(`NotFound`)で、消さない。"""

    @abstractmethod
    def list_records(
        self, record_filter: RecordFilter, sort: Sequence[SortKey], *, limit: int
    ) -> list[StoredRecord]:
        """条件に合う記録を、直前の書き込みを含む最新の状態で、最大 `limit` 件返す。

        一部のシャードの失敗・タイムアウトで欠けた一覧は成功にしない
        (`StoreUnavailableError("search_incomplete")`)。
        `limit` は 1 以上 `LIST_MAX_SIZE` 以下(超えるものは `ValueError`)。件数が上限を
        超えうる記録は、一覧ではなく `scan` で読む。値のない項目は並べ替えの末尾に置く。
        """

    @abstractmethod
    def scan(
        self, record_filter: RecordFilter, *, sort: Sequence[SortKey]
    ) -> AbstractContextManager[RecordPages]:
        """条件に合う記録を、最後まで、ページ単位で読む。`with` で使う。

        ```
        with repository.scan(record_filter, sort=[SortKey("document_id")]) as pages:
            for page in pages:
                ...
        ```

        - 契約: 開始の前に対象の索引を refresh する(書いた直後の記録の見落としを防ぐ。
          呼び出し側が個別に呼ぶ操作にはしない)。開始時点の状態を読む(走査中に書かれた・消された
          記録の影響を受けない。PIT)。
        - 走査を閉じる(`with` を抜ける)と、終了・失敗・中断のいずれでも PIT を閉じる。
        - PIT の保持時間(`RepositorySettings.scan_pit_keep_alive_seconds`)は、ページを 1 つ
          読むたびに延長される。呼び出し側が 1 ページの処理に保持時間を超える時間をかけると、
          次のページで PIT が期限切れになり、`StoreUnavailableError("pit_expired")` になる
          (走査をやり直す)。1 ページの処理は、保持時間より十分短くすること。
        - 検索のタイムアウト・一部のシャードの失敗で欠けた結果は成功にしない
          (`StoreUnavailableError("search_incomplete")`)。`sort` の値が同じ記録が隣り合って
          返ったときは、取りこぼしを避けるため `StoreUnexpectedResponseError("non_unique_sort")`。
        - `sort` は、記録ごとに一意な並びになる組にすること(呼び出し側が保証する。`search_after`
          が取りこぼし・重複を起こさないため)。`skip`・`oversize` 記録は、`record_type` ごとに
          別々に走査し、`document_id` で並べる(architecture 3.1)。
        - どの記録を消すかの判断は呼び出し側。ここは走査の仕組みと PIT の管理まで。
        """

    @abstractmethod
    def delete_ids(self, record_ids: Sequence[str]) -> BulkDeleteResult:
        """ID の一覧を削除する。1 回の件数の上限ごとに分けて送る。

        存在しない ID は成功とみなす(再実行で冪等にするため)。一部の ID だけ失敗したときは、
        失敗した ID を `BulkDeleteResult.failed_ids` で返す(リトライは呼び出し側が、失敗した ID
        だけに対して行う)。全体の異常は `StoreUnavailableError`(すでに消した分は戻らないが、
        冪等なので全体を再実行してよい)。
        """

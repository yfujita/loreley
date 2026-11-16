"""`loreley-sources` の読み書き(module 4.3。architecture 3.2・8.1。crawler-api 4.4)。

- `SourceReader`: 読み取りと一覧(`jobs`・`scheduler`・`crawl` が使う)。1 回の読み取りは、
  レコード全体を 1 つの値で返す(`crawl` が設定を 1 度だけ読むため。CA-P-51)。
- `SourceStore`: 登録・更新・`deleting` への更新・削除(`api`・`source_delete` が使う)。
  **`loreley-sources` に書く唯一のモジュール**(R7)。書き込みはすべて、`create` か、読んだ版を
  条件にした置き換え・削除で、版条件なしの書き込みはしない。

リトライの分担: 登録・更新は HTTP ハンドラから直接呼ばれ、呼び出し側にリトライの場がないので、
`SourceStore` が Store 層の全体の異常(`StoreUnavailableError`)を、操作全体(読み・比較・
書き)を単位にリトライする。
内容の比較で成否を決めるので、応答が失われた書き込みの再実行は、すでに成功していた場合も
成功になる(登録は 200、更新は変更なし)。読み取り・`mark_deleting`・`delete` は 1 回の試行で、
`StoreUnavailableError` はそのまま送出する(呼び出し側の `JobContext` などがリトライする)。
競合(版が合わない)は読み直して判定し直し、解けなければ `StoreUnavailableError`(503)。
"""

from typing import Any

from loreley_crawler.common.clock import Clock
from loreley_crawler.common.errors import (
    StoreUnavailableError,
    StoreUnexpectedResponseError,
    is_store_unavailable,
)
from loreley_crawler.common.retry import Retrier
from loreley_crawler.infrastructure.opensearch import (
    LIST_MAX_SIZE,
    Deleted,
    RecordFilter,
    Repository,
    SortKey,
    StoredRecord,
    Written,
)
from loreley_crawler.sources.records import (
    NewSource,
    SourceRecord,
    SourceSettingsInput,
    SourceStatus,
    StoredSource,
    build_body,
    parse_stored_source,
)
from loreley_crawler.sources.results import (
    AlreadyRegistered,
    DeleteSourceResult,
    MarkDeletingResult,
    MarkedDeleting,
    Registered,
    RegisterResult,
    RegistrationConflict,
    SourceDeleted,
    SourceIsDeleting,
    SourceNotDeleting,
    SourceNotFound,
    Unchanged,
    Updated,
    UpdateResult,
)

# 競合を読み直して判定し直す回数(仮値。単一の書き手では、通常は 1 回で解ける)。
DEFAULT_MAX_CONFLICT_ATTEMPTS = 5


class SourceReader:
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def fetch(self, source_id: str) -> StoredSource | None:
        stored = self._repository.fetch(source_id)
        return parse_stored_source(stored) if stored is not None else None

    def list_sources(self) -> list[StoredSource]:
        return self._list(RecordFilter())

    def list_scheduled_active_sources(self) -> list[StoredSource]:
        """`schedule_cron` が設定された `active` のソース(`scheduler` が使う)。"""
        return self._list(
            RecordFilter(
                equals={"status": SourceStatus.ACTIVE.value},
                exists=("schedule_cron",),
            )
        )

    def _list(self, record_filter: RecordFilter) -> list[StoredSource]:
        records = self._repository.list_records(
            record_filter, [SortKey("source_id")], limit=LIST_MAX_SIZE
        )
        # ソースの数は少ない前提。上限に達したら、取りこぼした一覧を成功にしない。
        if len(records) >= LIST_MAX_SIZE:
            raise StoreUnexpectedResponseError("source_list_truncated")
        return [parse_stored_source(record) for record in records]


class SourceStore(SourceReader):
    def __init__(
        self,
        repository: Repository,
        clock: Clock,
        retrier: Retrier,
        *,
        max_conflict_attempts: int = DEFAULT_MAX_CONFLICT_ATTEMPTS,
    ) -> None:
        super().__init__(repository)
        self._clock = clock
        self._retrier = retrier
        self._max_conflict_attempts = max_conflict_attempts

    # --- 登録・更新(HTTP ハンドラから。リトライは操作全体) ---

    def register(self, new_source: NewSource) -> RegisterResult:
        return self._retrier.run(
            lambda: self._register_once(new_source), is_retryable_error=is_store_unavailable
        )

    def update(self, source_id: str, settings: SourceSettingsInput) -> UpdateResult:
        return self._retrier.run(
            lambda: self._update_once(source_id, settings), is_retryable_error=is_store_unavailable
        )

    # --- ソース削除ジョブ(Job Runner から。リトライは呼び出し側) ---

    def mark_deleting(self, source_id: str) -> MarkDeletingResult:
        """`status=deleting` にする(順 0)。ほかの項目と `updated_at` は変えない。

        形式が不正な記録も `deleting` にできる(削除の前進を、不正な値で止めないため)。
        """
        for _ in range(self._max_conflict_attempts):
            stored = self._repository.fetch(source_id)
            if stored is None:
                return SourceNotFound()
            if stored.source.get("status") == SourceStatus.DELETING.value:
                return MarkedDeleting()
            body = {**stored.source, "status": SourceStatus.DELETING.value}
            if self._replace(stored, body) is not None:
                return MarkedDeleting()
        raise StoreUnavailableError("source_update_contention")

    def delete(self, source_id: str) -> DeleteSourceResult:
        """設定を削除する(順 5)。すでになければ成功。`deleting` でなければ削除しない。"""
        for _ in range(self._max_conflict_attempts):
            stored = self._repository.fetch(source_id)
            if stored is None:
                return SourceDeleted()
            if stored.source.get("status") != SourceStatus.DELETING.value:
                return SourceNotDeleting()
            outcome = self._repository.delete_if_unchanged(
                source_id, seq_no=stored.seq_no, primary_term=stored.primary_term
            )
            if isinstance(outcome, Deleted):
                return SourceDeleted()
        raise StoreUnavailableError("source_delete_contention")

    # --- 内部 ---

    def _register_once(self, new_source: NewSource) -> RegisterResult:
        for _ in range(self._max_conflict_attempts):
            body = build_body(
                new_source.source_id,
                new_source.connector_type,
                new_source.settings,
                status=SourceStatus.ACTIVE,
                updated_at=self._clock.now(),
            )
            outcome = self._repository.create(new_source.source_id, body)
            if isinstance(outcome, Written):
                stored = StoredRecord(
                    new_source.source_id, body, outcome.seq_no, outcome.primary_term
                )
                return Registered(self._parsed_record(stored))
            # `AlreadyExists`。同じ内容の登録済みか、別の設定かを読んで判定する。
            existing = self.fetch(new_source.source_id)
            if existing is None:
                continue  # 読む前に消えた(ソース削除の完了)。作り直す
            return _judge_existing(new_source, existing)
        raise StoreUnavailableError("source_register_contention")

    def _update_once(self, source_id: str, settings: SourceSettingsInput) -> UpdateResult:
        for _ in range(self._max_conflict_attempts):
            stored = self._repository.fetch(source_id)
            if stored is None:
                return SourceNotFound()
            existing = parse_stored_source(stored)
            if existing.status is SourceStatus.DELETING:
                return SourceIsDeleting()
            if existing.status is None:
                # `status` を保てない(`deleting` の取り違えを避けるため、書かない)。
                raise StoreUnexpectedResponseError("malformed_source_record")
            if isinstance(existing, SourceRecord) and _has_same_settings(existing, settings):
                return Unchanged(existing)
            body = build_body(
                source_id,
                _stored_connector_type(existing, stored),
                settings,
                status=existing.status,
                updated_at=self._clock.now(),
            )
            written = self._replace(stored, body)
            if written is not None:
                return Updated(self._parsed_record(written))
        raise StoreUnavailableError("source_update_contention")

    def _replace(self, stored: StoredRecord, body: dict[str, Any]) -> StoredRecord | None:
        """読んだ版を条件に置き換える。成功したら新しい版つきの記録、競合なら None。"""
        outcome = self._repository.replace_if_unchanged(
            stored.id, body, seq_no=stored.seq_no, primary_term=stored.primary_term
        )
        if not isinstance(outcome, Written):
            return None  # 版の不一致(記録の消失を含む)。読み直して判定し直す
        return StoredRecord(stored.id, body, outcome.seq_no, outcome.primary_term)

    @staticmethod
    def _parsed_record(stored: StoredRecord) -> SourceRecord:
        parsed = parse_stored_source(stored)
        if not isinstance(parsed, SourceRecord):
            # 自分が書いた値が読み戻せない = Crawler の不具合。
            raise StoreUnexpectedResponseError("malformed_source_record")
        return parsed


def _judge_existing(new_source: NewSource, existing: StoredSource) -> RegisterResult:
    if existing.status is SourceStatus.DELETING:
        return RegistrationConflict(SourceStatus.DELETING)
    if (
        isinstance(existing, SourceRecord)
        and existing.connector_type == new_source.connector_type
        and _has_same_settings(existing, new_source.settings)
    ):
        return AlreadyRegistered(existing)
    return RegistrationConflict(existing.status)


def _stored_connector_type(existing: StoredSource, stored: StoredRecord) -> str:
    """更新で保つ `connector_type`(登録後は変更できない)。"""
    if isinstance(existing, SourceRecord):
        return existing.connector_type
    connector_type = stored.source.get("connector_type")
    if not isinstance(connector_type, str):
        # 形式が不正で、保つ値がない。作り直しは管理者が(ソース削除と再登録で)行う。
        raise StoreUnexpectedResponseError("malformed_source_record")
    return connector_type


def _has_same_settings(existing: SourceRecord, settings: SourceSettingsInput) -> bool:
    """内容の比較規則(crawler-api 4.4.2): `status`・`updated_at` は比べない。

    `ratio_threshold` は数値として比べる(`1` と `1.0` は等しい)。キーの順は無視する。
    `connector_config` は、JSON の型の違い(`1` と `1.0`、`1` と `true`)を同じとみなさない
    (迷うときは書き込む側に倒す)。
    """
    return (
        existing.ttl == settings.ttl
        and existing.ratio_threshold == settings.ratio_threshold
        and existing.min_delete_count == settings.min_delete_count
        and existing.schedule_cron == settings.schedule_cron
        and _is_same_json_value(existing.connector_config, settings.connector_config)
    )


def _is_same_json_value(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            _is_same_json_value(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _is_same_json_value(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right

"""削除判定(arch 9.7 の順3〜5、9.6、9.3)。

順3: ID 一覧の上限超過・件数照合 → 順4: 削除対象の決定(0 件なら `deleted`)→
順5: T > D のガード(案。U-33)・割合ルール・最小件数ルール・強制削除モード。
順1(先行待ち)・順2(メンテナンスフラグ)は、結果を書く側(`DeletionProcessor`)が先に行う。

件数と対象の取り込みは、判定の先頭で 1 回 `refresh` した後の状態を使う(9.3、9.14)。
判定時刻は 1 回だけ決めて固定する(9.8)。設定は、開始通知から複写した値(`DeletionResultRecord`)
だけを使う。結果は書かず、結果の書き込みは呼び出し側が行う。
"""

from collections.abc import Collection
from dataclasses import dataclass, replace

from loreley_indexer.common.clock import Clock
from loreley_indexer.crawl_runs.deletion.judgment import (
    Measurements,
    passes_ratio_rule,
    ttl_cutoff,
)
from loreley_indexer.crawl_runs.deletion.result_writer import TerminalTransition
from loreley_indexer.crawl_runs.deletion.targets import TargetCollector, TargetLimitExceeded
from loreley_indexer.crawl_runs.lifecycle import (
    DeletionReason,
    DeletionResultRecord,
    DeletionStatus,
    MalformedRecordError,
)
from loreley_indexer.infrastructure.opensearch import DocumentFilter, SearchIndexRepository

TARGET_LIMIT_EXCEEDED = "target_limit_exceeded"  # `delete_error` の `reason_detail`


@dataclass(frozen=True)
class Verdict:
    """削除せずに(または削除対象 0 件で)終わる判定。終端状態の書き込みに使う。"""

    transition: TerminalTransition
    measurements: Measurements
    deleted_count: int | None = None


@dataclass(frozen=True)
class Execution:
    """削除を実行する判定。`targets` は空でなく、`document_id` の昇順。"""

    targets: list[str]
    measurements: Measurements


class DeletionJudge:
    def __init__(
        self, *, search_index: SearchIndexRepository, clock: Clock, collector: TargetCollector
    ) -> None:
        self._search_index = search_index
        self._clock = clock
        self._collector = collector

    def judge(self, record: DeletionResultRecord) -> Verdict | Execution:
        if record.skip_and_oversize_id_limit_exceeded:
            # 保存されていない ID 一覧では `E_missing` を数えられない(K34)。
            return _validation_failed(DeletionReason.ID_LIMIT_EXCEEDED, Measurements())
        if record.enumerated_count is None:
            raise MalformedRecordError("enumerated_count")
        excluded = _excluded_ids(record)

        self._search_index.refresh()
        n_seen = self._search_index.count(
            DocumentFilter(source_id=record.source_id, last_seen_at_gte=record.crawl_started_at)
        )
        e_missing = self._count_missing(excluded)
        counted = Measurements(n_seen=n_seen, e_missing=e_missing)
        if record.enumerated_count != n_seen + e_missing:
            return _validation_failed(DeletionReason.COUNT_MISMATCH, counted)
        return self._decide_targets(record, excluded, counted)

    def _decide_targets(
        self, record: DeletionResultRecord, excluded: Collection[str], counted: Measurements
    ) -> Verdict | Execution:
        cutoff = ttl_cutoff(self._clock.now(), record.ttl)
        try:
            targets = self._collector.collect(
                source_id=record.source_id, cutoff=cutoff, excluded=excluded
            )
        except TargetLimitExceeded:
            failed = TerminalTransition(
                DeletionStatus.FAILED,
                DeletionReason.DELETE_ERROR,
                reason_detail=TARGET_LIMIT_EXCEEDED,
            )
            return Verdict(failed, counted)
        denominator = self._search_index.count(DocumentFilter(source_id=record.source_id))
        measured = replace(counted, target_count=len(targets), denominator=denominator)

        if not targets:
            return Verdict(TerminalTransition(DeletionStatus.DELETED), measured, deleted_count=0)
        # 強制削除モードでも、T > D の確認は行う(U-33)。割合ルールの判定より前に確認する。
        if len(targets) > denominator:
            return _validation_failed(DeletionReason.TARGET_EXCEEDS_DENOMINATOR, measured)
        if not record.forced and not passes_ratio_rule(
            target_count=len(targets),
            denominator=denominator,
            min_delete_count=record.min_delete_count,
            ratio_threshold=record.ratio_threshold,
        ):
            return Verdict(TerminalTransition(DeletionStatus.SKIPPED_BY_RATIO), measured)
        return Execution(targets, measured)

    def _count_missing(self, excluded: Collection[str]) -> int:
        """`E_missing`: 保存した ID 一覧(和集合)のうち、検索インデックスにないものの件数。"""
        if not excluded:
            return 0
        return len(excluded) - self._search_index.count_existing_ids(sorted(excluded))


def _excluded_ids(record: DeletionResultRecord) -> frozenset[str]:
    """削除対象から除外するスキップ文書・サイズ超過文書の ID(保存した ID 一覧。K31)。"""
    if record.skipped_document_ids is None:
        raise MalformedRecordError("skipped_document_ids")
    if record.oversize_document_ids is None:
        raise MalformedRecordError("oversize_document_ids")
    return frozenset(record.skipped_document_ids) | frozenset(record.oversize_document_ids)


def _validation_failed(reason: DeletionReason, measurements: Measurements) -> Verdict:
    return Verdict(TerminalTransition(DeletionStatus.VALIDATION_FAILED, reason), measurements)

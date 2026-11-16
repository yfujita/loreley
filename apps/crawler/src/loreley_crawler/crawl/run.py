"""`CrawlRun`: 1 つのクロールジョブの実行状態と、実行開始の後の段階(module 4.5)。

実行開始(`prepare_crawl`)が整えたものを受けて、次の段階を進める。段階の順は architecture 4.5:
- 手順 9: `send_start_notice`(開始通知)
- 手順 10: `process_chunks`(チャンク処理: `last-seen` -> 取得 -> バッチ登録を、取得と登録を交互に)
- 手順 11: `finalize_registration`(0 件列挙の警告と、登録結果を `partial=false` で確定する)、
  `purge_document_records`(スキップ記録・原本サイズ超過記録の整理)、`send_finish_notice`
  (終了通知の固定・送信。202 は受理の確認ではない)
- 手順 12: `poll_deletion_status`(削除結果のポーリングと、確認結果の区分)
- 手順 13: 最終状態の記録は呼び出し側(`CrawlExecutor`)。`final_changes` が記録の内容を作る

状態: 登録結果の集計と ID 集合(`tally`)、列挙の包み(`enumeration`)、識別子エラーの例
(`invalid_id_examples`)、警告(`warnings`)、設定スナップショット(`snapshot`)、開始通知の成否
(`start_notice_sent`)、`enumeration_completed` の送信の開始(`finish_send_started`)。
`connector_config` は持たない(`prepare_crawl` の局所変数。R11)。

各段階は、失敗を `CrawlFailure`(ジョブを `failed` にすべき失敗)で、中断を `JobInterrupted` で、
Store 層の異常を `StoreUnavailableError` などで送出する。どう終えるか(最終状態・終了通知 `failed`・
`cancelled`)は呼び出し側(`CrawlExecutor`)が決める。リソース(列挙・Connector)は `close` で閉じる。
"""

import logging
from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import Any

from loreley_crawler.connectors.interface import (
    Completed,
    ConnectorError,
    ErrorCategory,
    ErrorScope,
    converting_unexpected_errors,
)
from loreley_crawler.crawl.batch_registration import (
    BatchBuilder,
    BatchRegistrar,
    PendingDocument,
)
from loreley_crawler.crawl.constants import LOCAL_CHECKS, NO_CHECKS
from loreley_crawler.crawl.dependencies import CrawlDependencies
from loreley_crawler.crawl.failure import CrawlFailure
from loreley_crawler.crawl.fetch_stage import FetchStage
from loreley_crawler.crawl.finish_notice import FinishNotice, fixed_instant
from loreley_crawler.crawl.indexer_calls import IndexerCaller
from loreley_crawler.crawl.outcomes import DocumentOutcomeRecorder
from loreley_crawler.crawl.skip_counter import ConsecutiveSkipCounter
from loreley_crawler.crawl.snapshot import SettingsSnapshot
from loreley_crawler.crawl.start import PreparedCrawl
from loreley_crawler.crawl.status_polling import (
    PollingResult,
    StatusPoller,
    deletion_summary_record,
)
from loreley_crawler.crawl.tally import RegistrationTally
from loreley_crawler.crawl.warning_log import (
    ENUMERATED_ZERO_AFTER_NONZERO,
    FINISH_ID_LIST_OVER_THRESHOLD,
    INVALID_EXTERNAL_ID,
    WarningLog,
)
from loreley_crawler.documents import (
    DocumentEnumeration,
    DocumentFetcher,
    EnumeratedDocument,
    EnumerationTooLargeError,
    InvalidExternalId,
)
from loreley_crawler.infrastructure.indexer_client import FinishOutcome
from loreley_crawler.jobs import Check, DocumentRecordType, FailureReason, JobContext

logger = logging.getLogger(__name__)

COUNT_CHECK_FAILED_DETAIL = (
    "列挙した文書の数が、登録・スキップ・原本サイズ超過の合計と一致しない(終了通知を送らない)"
)


class CrawlRun:
    def __init__(
        self, *, prepared: PreparedCrawl, context: JobContext, dependencies: CrawlDependencies
    ) -> None:
        self._prepared = prepared
        self._context = context
        self._dependencies = dependencies
        self._settings = dependencies.settings
        self._tally = RegistrationTally()
        skip_counter = ConsecutiveSkipCounter(self._settings.consecutive_skip_limit)
        outcomes = DocumentOutcomeRecorder(
            context=context,
            source_id=prepared.source_id,
            document_records=dependencies.document_records,
            tally=self._tally,
            skip_counter=skip_counter,
        )
        self._indexer = IndexerCaller(
            context=context,
            client=dependencies.indexer_client,
            source_id=prepared.source_id,
            lock=prepared.lock,
            snapshot=prepared.snapshot,
            last_seen_max_ids=self._settings.last_seen_max_ids,
        )
        self._fetch_stage = FetchStage(
            context=context,
            fetcher=DocumentFetcher(prepared.connector, settings=dependencies.documents_settings),
            outcomes=outcomes,
            skip_counter=skip_counter,
        )
        self._registrar = BatchRegistrar(
            indexer=self._indexer, outcomes=outcomes, tally=self._tally, skip_counter=skip_counter
        )
        self._clock = dependencies.clock
        self._warnings = WarningLog(self._settings.warnings_max_entries)
        self._poller = StatusPoller(
            context=context,
            indexer=self._indexer,
            settings=self._settings,
            clock=self._clock,
            warnings=self._warnings,
        )
        self._start_notice_sent = False
        self._finish_send_started = False
        self._is_closed = False
        self._enumeration: DocumentEnumeration | None = None
        self._invalid_id_examples: list[InvalidExternalId] = []
        self._flushed_registration: dict[str, Any] | None = None
        self._flushed_warnings: list[dict[str, Any]] | None = None

    # --- 状態(6b も使う) ---

    @property
    def source_id(self) -> str:
        return self._prepared.source_id

    @property
    def snapshot(self) -> SettingsSnapshot:
        return self._prepared.snapshot

    @property
    def start_notice_sent(self) -> bool:
        """開始通知が成功した後か。終了通知 `failed` を送ってよい条件の 1 つ(architecture 4.8)。"""
        return self._start_notice_sent

    @property
    def finish_send_started(self) -> bool:
        """`enumeration_completed` の初回の送信を始めた後か(`send_started_at` を記録した後。4.7)。

        始めた後は、取り消しても削除を止められず、終了通知 `failed`・`cancelled` を送らない。
        """
        return self._finish_send_started

    @property
    def warnings(self) -> WarningLog:
        return self._warnings

    @property
    def tally(self) -> RegistrationTally:
        return self._tally

    @property
    def enumeration(self) -> DocumentEnumeration | None:
        """列挙を始める前は None。`enumerated_count`・`has_enumerated` はここに問い合わせる。"""
        return self._enumeration

    @property
    def invalid_id_examples(self) -> tuple[InvalidExternalId, ...]:
        """識別子エラーの例(`warnings` 用。上限つき)。件数は `tally.invalid_id_count`。"""
        return tuple(self._invalid_id_examples)

    def registration_record(self) -> dict[str, Any]:
        """ジョブ記録の `registration`(いまの集計。列挙前は 0 件・`partial=true`)。"""
        enumerated_count = self._enumeration.enumerated_count if self._enumeration else 0
        return self._tally.to_record(enumerated_count=enumerated_count)

    # --- 段階 ---

    def send_start_notice(self) -> None:
        """開始通知(手順 9)。失敗は `CrawlFailure`(`indexer_unavailable`・`indexer_rejected`)。"""
        self._indexer.start_crawl()
        self._start_notice_sent = True

    def process_chunks(self) -> None:
        """列挙が `Completed` になり、すべての応答を確認し終えるまで、チャンクを処理する(手順 10)。

        列挙の失敗は、以降のチャンクを処理せず `CrawlFailure` にする。それまでに登録した文書は
        そのまま残る(architecture 4.6)。
        """
        enumeration = self._open_enumeration()
        while True:
            chunk, is_completed = self._read_chunk(enumeration)
            if chunk:
                self._process_chunk(chunk)
            if is_completed:
                return

    def finalize_registration(self) -> None:
        """警告を残し、登録結果を `partial=false` で確定する(手順 11。確定の後は戻さない)。

        0 件列挙の警告は、確定の前に判定する(architecture 7.7。CA-P-52)。警告は観測だけで、
        ジョブの status・終了通知・削除の挙動は変えない。
        """
        self._warn_about_invalid_ids()
        self._warn_about_zero_enumeration()
        self._tally.finalize()
        self._flush_registration()
        self._flush_warnings()

    def purge_document_records(self) -> None:
        """スキップ記録・原本サイズ超過記録を整理する(手順 11。architecture 6.4)。

        列挙が `Completed` で、すべての応答を確認し終えた後にだけ呼ぶ(失敗したクロールで消すと、
        残すべき記録を失う)。記録の種類ごとに、今回もその種類の結果になった文書の記録だけを残す
        (`skip` は今回スキップした文書、`oversize` は今回サイズ超過だった文書)。それ以外
        (今回登録できた・別の種類の結果になった・列挙されなかった文書)の記録は消す。
        """
        retrier = self._context.retrier(LOCAL_CHECKS)
        for record_type in DocumentRecordType:
            self._dependencies.document_records.purge(
                source_id=self.source_id,
                record_type=record_type,
                should_delete=partial(self._should_delete_record, record_type),
                retrier=retrier,
            )

    def send_finish_notice(self) -> None:
        """終了通知(`enumeration_completed`)を固定して送る(手順 11。architecture 7.5)。

        次の順に行う。(1)ID 一覧の警告閾値を確認する。(2)内容を組み立てて `finish_notice` に
        保存して固定する(送信前。再送は同じ内容)。(3)取り消し・所有権・メンテナンスを確認する
        (削除の判断のきっかけになる通知なので、喪失・メンテナンス中は送らない)。(4)送信の開始を
        `send_started_at` に記録する(取り消しが有効かの境界。4.7)。(5)送る。
        送信の確認点は取り消しだけ(終了通知は所有確認の対象外。5.7)で、取り消されたらリトライをやめる。
        202 は受理の確認ではない(確認はポーリング)。失敗は `finish_notice_failed`(尽きた・409)か
        `indexer_rejected`。
        """
        enumeration = self._require_enumeration()
        self.check_the_counts_add_up()
        skipped_ids = self._tally.skipped_document_ids
        oversize_ids = self._tally.oversize_document_ids
        id_count = len(skipped_ids) + len(oversize_ids)
        if id_count > self._settings.finish_id_list_warning_threshold:
            # 超えると Indexer が削除の判定を `validation_failed`(`id_limit_exceeded`)にする(7.5)。
            self._warnings.add(
                FINISH_ID_LIST_OVER_THRESHOLD,
                count=id_count,
                threshold=self._settings.finish_id_list_warning_threshold,
            )
            self._flush_warnings()
        notice = FinishNotice.enumeration_completed(
            now=self._clock.now(),
            enumerated_count=enumeration.enumerated_count,
            skipped_document_ids=skipped_ids,
            oversize_document_ids=oversize_ids,
        )
        self._save_finish_notice(notice, send_started_at=None)
        self._context.check(Check.ALL)
        self._save_finish_notice(notice, send_started_at=fixed_instant(self._clock.now()))
        self._finish_send_started = True
        self._indexer.finish_crawl(notice, checks=Check.CANCELLATION)

    def check_the_counts_add_up(self) -> None:
        """列挙した文書は、登録されたか、スキップか原本サイズ超過のどれかでなければならない。

        件数照合(Indexer は `enumerated_count == N_seen + E_missing` のときだけ削除を判断する。
        architecture 7.5)の、Crawler 側の局所的な不変条件。成り立たなければ、`CrawlFailure`
        (`internal_error`。Crawler の不具合。値は載せない)にする。壊れた集計をもとに、記録の整理も
        削除の判断のきっかけになる通知も行わないよう、**整理の前**(登録結果の確定の直後)に呼ぶ。
        `send_finish_notice` も、送信の前に確認する(二重防御。安価な足し算)。
        """
        enumerated_count = self._require_enumeration().enumerated_count
        accounted_for = (
            self._tally.registered_count
            + len(self._tally.skipped_document_ids)
            + len(self._tally.oversize_document_ids)
        )
        if enumerated_count != accounted_for:
            raise CrawlFailure(FailureReason.INTERNAL_ERROR, COUNT_CHECK_FAILED_DETAIL)

    def poll_deletion_status(self) -> PollingResult:
        """削除結果が終端状態になるまでポーリングする(手順 12。確認結果の区分を返す)。"""
        return self._poller.poll()

    def notify_outcome(self, outcome: FinishOutcome) -> None:
        """終了通知 `failed`・`cancelled` を、可能なら送る(届かなくてよい。architecture 4.7・4.8)。

        開始通知が成功した後で、`enumeration_completed` の初回の送信を始める前に限る。
        送信を始めた後は、受理の有無が不明で、別の内容は Indexer が 409
        `finish_content_mismatch` で拒否し、元の `failure_reason` を `finish_notice_failed` に
        上書きしかねないので送らない。内容は `outcome`・`source_id`・`finished_at` だけで、
        送る前に `finish_notice` に固定する(固定済みの `enumeration_completed` は、まだ届いて
        いないので置き換える)。確認点は通さない(所有・取り消し・メンテナンスの確認の対象外)。
        失敗は握りつぶして記録する(呼び出し側の最終状態の記録を妨げない)。
        """
        if not self._start_notice_sent or self._finish_send_started:
            return
        try:
            notice = FinishNotice.without_counts(outcome, now=self._clock.now())
            self._save_finish_notice(notice, send_started_at=None)
            self._indexer.finish_crawl(notice, checks=NO_CHECKS)
        except Exception as error:
            logger.warning(
                "could not send the %s finish notice: error=%s", outcome.value, type(error).__name__
            )

    def abort_polling_on_cancel(self) -> PollingResult | None:
        """ポーリング中に取り消されたとき、確認を打ち切る(`unconfirmed`。警告を残す)。

        ポーリングに入っていなければ None(確認結果の区分は書かない)。
        """
        return self._poller.abort_on_cancel()

    def final_changes(self, polling: PollingResult | None) -> dict[str, Any]:
        """最終状態と一緒に記録する項目(JSON の型): 登録結果・警告・確認結果の区分・削除結果の要約。

        登録結果は、確定前なら `partial=true` のまま(確定後は `false`。CA-K-15)。
        `polling` が None なら、確認結果の区分は書かない(確認に入っていない・終えられなかった)。
        """
        changes: dict[str, Any] = {"registration": self.registration_record()}
        if polling is not None:
            changes["confirmation"] = polling.confirmation.value
            summary = deletion_summary_record(polling)
            if summary is not None:
                changes["deletion_summary"] = summary
        warnings = self._warnings.to_record()
        if warnings:
            changes["warnings"] = warnings
        return changes

    def close(self) -> None:
        """列挙と Connector を閉じる(正常・異常・取り消しのいずれでも)。何度呼んでもよい。"""
        if self._is_closed:
            return
        self._is_closed = True
        if self._enumeration is not None:
            _close_quietly(self._enumeration.close, "enumeration")
        _close_quietly(self._prepared.connector.close, "connector")

    def _require_enumeration(self) -> DocumentEnumeration:
        if self._enumeration is None:
            raise RuntimeError("the enumeration has not started")
        return self._enumeration

    def _save_finish_notice(
        self, notice: FinishNotice, *, send_started_at: datetime | None
    ) -> None:
        self._context.update(
            {"finish_notice": notice.to_record(self.source_id, send_started_at=send_started_at)}
        )

    def _warn_about_invalid_ids(self) -> None:
        if self._tally.invalid_id_count == 0:
            return
        self._warnings.add(
            INVALID_EXTERNAL_ID,
            count=self._tally.invalid_id_count,
            examples=[
                {"reason": example.error.message, "external_id": example.display_external_id}
                for example in self._invalid_id_examples
            ],
        )

    def _warn_about_zero_enumeration(self) -> None:
        """今回 0 件で、直前に完了したクロールが 1 件以上なら警告する(マウント外れの手がかり)。"""
        if self._require_enumeration().enumerated_count != 0:
            return
        previous = self._dependencies.job_history.find_previous_completed_crawl(
            source_id=self.source_id,
            excluding_job_id=self._context.job_id,
            max_jobs=self._settings.previous_crawl_lookup_jobs,
            retrier=self._context.retrier(LOCAL_CHECKS),
        )
        if previous is not None and previous.enumerated_count >= 1:
            self._warnings.add(
                ENUMERATED_ZERO_AFTER_NONZERO,
                previous_job_id=previous.job_id,
                previous_enumerated_count=previous.enumerated_count,
            )

    def _flush_warnings(self) -> None:
        warnings = self._warnings.to_record()
        if not warnings or warnings == self._flushed_warnings:
            return
        self._context.update({"warnings": warnings})
        self._flushed_warnings = warnings

    # --- チャンク処理 ---

    def _open_enumeration(self) -> DocumentEnumeration:
        try:
            with converting_unexpected_errors(ErrorScope.SOURCE):
                stream = self._prepared.connector.enumerate()
        except ConnectorError as error:
            raise _enumeration_failure(error) from None
        self._enumeration = DocumentEnumeration(
            stream,
            source_id=self.source_id,
            settings=self._dependencies.documents_settings,
        )
        return self._enumeration

    def _read_chunk(
        self, enumeration: DocumentEnumeration
    ) -> tuple[list[EnumeratedDocument], bool]:
        """チャンクが満ちるか列挙が完了するまで読む。完了したら True。識別子エラーはここで計上する。

        チャンクの件数に数えるのは、`last-seen`・取得の対象になる文書だけ。
        """
        chunk: list[EnumeratedDocument] = []
        while len(chunk) < self._settings.chunk_size:
            self._context.check(LOCAL_CHECKS)
            try:
                result = enumeration.next()
            except ConnectorError as error:
                raise _enumeration_failure(error) from None
            except EnumerationTooLargeError as error:
                raise CrawlFailure(
                    FailureReason.ENUMERATION_TOO_LARGE,
                    f"列挙した文書数が上限 {error.max_enumerated_documents} 件を超えた",
                ) from None
            if isinstance(result, Completed):
                return chunk, True
            if isinstance(result, InvalidExternalId):
                self._record_invalid_id(result)
                continue
            chunk.append(result)
        return chunk, False

    def _record_invalid_id(self, invalid: InvalidExternalId) -> None:
        """識別子エラー: 登録も `last-seen` もしない。計数もリセットもしない(architecture 6.3)。"""
        self._tally.record_invalid_id()
        if len(self._invalid_id_examples) < self._settings.invalid_id_example_limit:
            self._invalid_id_examples.append(invalid)

    def _process_chunk(self, chunk: list[EnumeratedDocument]) -> None:
        """`last-seen` -> 取得 -> バッチ登録の順に処理する(`last-seen` は取得より前。4.6)。

        取得と登録は交互に進め、保持する原本はバッチ 1 つ分まで。
        """
        self._indexer.report_last_seen([document.document_id for document in chunk])
        batch = BatchBuilder(
            max_documents=self._settings.batch_max_documents,
            max_raw_bytes=self._settings.batch_max_raw_bytes,
        )
        for document in chunk:
            prepared = self._fetch_stage.fetch(document)
            if prepared is None:
                continue
            pending = PendingDocument.of(document, prepared)
            if batch.would_exceed_bytes(pending):
                self._register(batch.drain())
            batch.add(pending)
            if batch.is_full:
                self._register(batch.drain())
        if len(batch) > 0:
            self._register(batch.drain())
        self._flush_registration()

    def _register(self, pending: list[PendingDocument]) -> None:
        self._registrar.register(pending)
        self._flush_registration()

    def _flush_registration(self) -> None:
        """集計をジョブ記録に反映する(バッチの応答ごと・チャンクの終わり。変わったときだけ)。"""
        registration = self.registration_record()
        if registration == self._flushed_registration:
            return
        self._context.update({"registration": registration})
        self._flushed_registration = registration

    def _should_delete_record(self, record_type: DocumentRecordType, document_id: str) -> bool:
        enumeration = self._enumeration
        if enumeration is None or not enumeration.has_enumerated(document_id):
            return True  # 今回列挙されなかった(元ファイルが消えた)
        if record_type is DocumentRecordType.SKIP:
            return not self._tally.is_skipped(document_id)
        return not self._tally.is_oversize(document_id)


def _enumeration_failure(error: ConnectorError) -> CrawlFailure:
    """列挙の失敗(`Failed`)をジョブの失敗にする。説明は分類名と、Connector の説明文。"""
    if error.category is ErrorCategory.EXTERNAL_ID_COLLISION:
        return CrawlFailure(FailureReason.EXTERNAL_ID_COLLISION, error.message)
    return CrawlFailure(
        FailureReason.ENUMERATION_FAILED, f"{error.category.value}: {error.message}"
    )


def _close_quietly(close: Callable[[], None], name: str) -> None:
    try:
        close()
    except Exception as error:
        # 閉じるのに失敗しても、元の結果(最終状態の記録)を妨げない。例外の種類だけを出す(R11)。
        logger.warning("failed to close %s: error=%s", name, type(error).__name__)

"""`latest_for_source`・`rerunnable`・`rerun_blocked_reason`・`cancel_after_finish_notice`(C 5.3)。

`rerunnable` は、画面が再実行の操作を出し分けるための導出で、サーバーでは強制しない(B 2.9)。
"""

from dataclasses import dataclass
from enum import StrEnum

from loreley_api.admin.base.codes import JobStatus, JobType, RerunBlockedReason, SourceStatus
from loreley_api.admin.derivation.values import (
    Document,
    read_choice,
    read_instant,
    read_mapping,
)


class SourceCondition(StrEnum):
    """再実行の判定に使う、データソース設定の状態。"""

    ACTIVE = "active"
    DELETING = "deleting"
    # 設定がない(削除済み。`found=false`)。
    MISSING = "missing"
    # 設定の読み取りが失敗した。
    READ_FAILED = "read_failed"


class UndecidedBecause(StrEnum):
    """`rerunnable=null` の原因。`unavailable.rerunnable` の理由コードは、この失敗と同じになる。"""

    STALLED = "stalled"
    LATEST_FOR_SOURCE = "latest_for_source"
    SOURCE = "source"


@dataclass(frozen=True)
class RerunDecision:
    rerunnable: bool | None
    blocked_reason: RerunBlockedReason | None
    undecided_because: UndecidedBecause | None = None


def source_condition_of(source: Document | None) -> SourceCondition:
    """設定文書の `_source`(文書がなければ `None`)から。

    `deleting` 以外(読めない値を含む)は `active`。
    """
    if source is None:
        return SourceCondition.MISSING
    if read_choice(source.get("status"), SourceStatus) is SourceStatus.DELETING:
        return SourceCondition.DELETING
    return SourceCondition.ACTIVE


def is_latest_for_source(
    job_type: JobType | None, job_id: str, latest_crawl_id: str | None
) -> bool:
    """`crawl` ジョブだけ、そのソースの最新の `crawl` の ID と比べる。

    `source_delete` と、読めない `job_type`(`None`)は `false`。
    """
    return job_type is JobType.CRAWL and latest_crawl_id == job_id


def decide_rerun(
    *,
    job_type: JobType | None,
    status: JobStatus | None,
    stalled: bool | None,
    latest_for_source: bool | None,
    source: SourceCondition,
) -> RerunDecision:
    """C 5.3 の表を、順に評価して最初に決まったところで終える。

    `job_type`・`status` が読めない(`None`)ものは、確かめられないので再実行を出さない安全側。
    """
    if job_type is not JobType.CRAWL:
        return RerunDecision(False, RerunBlockedReason.NOT_CRAWL)
    if status is JobStatus.RUNNING:
        if stalled is None:
            return RerunDecision(None, None, UndecidedBecause.STALLED)
        if stalled:
            return RerunDecision(False, RerunBlockedReason.STALLED)
    if status is not JobStatus.FAILED:
        return RerunDecision(False, RerunBlockedReason.NOT_FAILED)
    if latest_for_source is None:
        return RerunDecision(None, None, UndecidedBecause.LATEST_FOR_SOURCE)
    if not latest_for_source:
        return RerunDecision(False, RerunBlockedReason.SUPERSEDED)
    match source:
        case SourceCondition.READ_FAILED:
            return RerunDecision(None, None, UndecidedBecause.SOURCE)
        case SourceCondition.MISSING:
            return RerunDecision(False, RerunBlockedReason.SOURCE_MISSING)
        case SourceCondition.DELETING:
            return RerunDecision(False, RerunBlockedReason.SOURCE_DELETING)
        case SourceCondition.ACTIVE:
            return RerunDecision(True, None)


def has_cancel_after_finish_notice(status: JobStatus | None, job_source: Document) -> bool:
    """`cancelled` で、終了通知の送信を始めた後に取消が受け付けられた。

    終了通知の `send_started_at` が日時として読めることが条件。
    """
    if status is not JobStatus.CANCELLED:
        return False
    finish_notice = read_mapping(job_source.get("finish_notice"))
    if finish_notice is None:
        return False
    return read_instant(finish_notice.get("send_started_at")) is not None

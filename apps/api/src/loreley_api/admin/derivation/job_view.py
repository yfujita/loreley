"""`JobBrief` の元・`registration`・`warnings`・`failure_detail`(C 5.4。B 2.11・5.2)。

ジョブ記録の値は、型が違う・許される値にないときは読めない値として `None` にする(未知の値を
通さない。C 5.0)。`stalled`・`cancellable` は、読み取りが要るので `stalled.py` と `services` が
決める(ここでは作らない)。
"""

from dataclasses import dataclass

from loreley_api.admin.base.codes import (
    DocumentExistence,
    JobStatus,
    JobTrigger,
    JobType,
    RegistrationPhase,
)
from loreley_api.admin.derivation.values import (
    Document,
    read_bool,
    read_choice,
    read_instant_text,
    read_int,
    read_mapping,
    read_non_empty_str,
    read_str,
)


@dataclass(frozen=True)
class JobBriefView:
    job_id: str
    source_id: str
    job_type: JobType | None
    trigger: JobTrigger | None
    status: JobStatus | None
    force_delete: bool | None
    rewrite_mode: bool | None
    queued_at: str | None
    started_at: str | None
    finished_at: str | None
    failure_reason: str | None


def read_job_brief(
    record_id: str, source: Document, *, fallback_source_id: str = ""
) -> JobBriefView:
    """ジョブ記録の `_source` から `JobBrief` の元を作る。

    `job_id` は文書の `_id`。`source_id` は、記録の値が文字列でなければ呼び出し側が持つ値
    (要求の絞り込み・集計のキー)で補い、`null` にしない(C 5.0)。補う値もなければ空文字列。
    """
    status = read_choice(source.get("status"), JobStatus)
    return JobBriefView(
        job_id=record_id,
        source_id=read_str(source.get("source_id")) or fallback_source_id,
        job_type=read_choice(source.get("job_type"), JobType),
        trigger=read_choice(source.get("trigger"), JobTrigger),
        status=status,
        force_delete=read_bool(source.get("force_delete")),
        rewrite_mode=read_bool(source.get("rewrite_mode")),
        queued_at=read_instant_text(source.get("queued_at")),
        started_at=read_instant_text(source.get("started_at")),
        finished_at=read_instant_text(source.get("finished_at")),
        # 理由コードは `failed` のときだけ。未知のコードも解釈せずそのまま返す。
        failure_reason=read_non_empty_str(source.get("failure_reason"))
        if status is JobStatus.FAILED
        else None,
    )


def read_failure_detail(source: Document, status: JobStatus | None) -> str | None:
    """`failed` のときだけ、文字列ならそのまま(Crawler が切り詰め・エスケープ済み。B 5.2)。"""
    if status is not JobStatus.FAILED:
        return None
    return read_str(source.get("failure_detail"))


def read_warnings(source: Document) -> list[dict[str, object]]:
    """配列のうち、オブジェクトで `code` が文字列のものを、そのまま通す(内容は解釈しない)。"""
    warnings = source.get("warnings")
    if not isinstance(warnings, list):
        return []
    entries = (read_mapping(warning) for warning in warnings)
    return [
        dict(entry) for entry in entries if entry is not None and isinstance(entry.get("code"), str)
    ]


@dataclass(frozen=True)
class RegistrationView:
    enumerated_count: int | None
    created_count: int | None
    updated_count: int | None
    unchanged_count: int | None
    skipped_count: int | None
    oversize_count: int | None
    error_count: int | None
    invalid_id_count: int | None
    partial: bool | None
    phase: RegistrationPhase | None


def read_registration(
    source: Document, job_type: JobType | None, status: JobStatus | None
) -> RegistrationView | None:
    """`source_delete` と、記録がない(実行待ち)ときは `None`。件数・`partial` は保存値のまま。"""
    if job_type is JobType.SOURCE_DELETE:
        return None
    registration = read_mapping(source.get("registration"))
    if registration is None:
        return None
    partial = read_bool(registration.get("partial"))
    return RegistrationView(
        enumerated_count=read_int(registration.get("enumerated_count")),
        created_count=read_int(registration.get("created_count")),
        updated_count=read_int(registration.get("updated_count")),
        unchanged_count=read_int(registration.get("unchanged_count")),
        skipped_count=read_int(registration.get("skipped_count")),
        oversize_count=read_int(registration.get("oversize_count")),
        error_count=read_int(registration.get("error_count")),
        invalid_id_count=read_int(registration.get("invalid_id_count")),
        partial=partial,
        phase=derive_phase(partial, status),
    )


def derive_phase(partial: bool | None, status: JobStatus | None) -> RegistrationPhase | None:
    """`partial=false` は `final`、`partial=true` は実行待ち・実行中なら `in_progress`、終端なら
    `incomplete`(確定前に終わった)。`partial` が読めない、または `partial=true` で `status` が
    読めないときは `None`。
    """
    if partial is None:
        return None
    if not partial:
        return RegistrationPhase.FINAL
    if status is None:
        return None
    if status in (JobStatus.QUEUED, JobStatus.RUNNING):
        return RegistrationPhase.IN_PROGRESS
    return RegistrationPhase.INCOMPLETE


def existence_of(document_id: str | None, existing_ids: frozenset[str] | None) -> DocumentExistence:
    """`skipped` タブの行の `existence`(C 5.6)。

    `existing_ids` は、そのページの `document_id` のうち検索インデックスにあるもの。一括検索が
    失敗して分からないとき(`None`)と、`document_id` が読めないときは `unknown`。
    """
    if document_id is None or existing_ids is None:
        return DocumentExistence.UNKNOWN
    if document_id in existing_ids:
        return DocumentExistence.EXISTING
    return DocumentExistence.NEW

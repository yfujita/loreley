"""`last_crawl`・`last_completed_at`・`delete_job`(EP-01・02。C 5.5)の元になる値。

R-3 の結果(ソースごとの最新ジョブと最終完了日時)から作る。`JobBrief` の `stalled`・
`cancellable` は `stalled.py`・`services` が決める。
"""

from datetime import UTC, datetime, timedelta

from loreley_api.admin.base.codes import SourceStatus
from loreley_api.common.timestamps import format_instant

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def last_completed_at_of(epoch_millis: int | None) -> str | None:
    """`succeeded`・`partially_succeeded` の `crawl` の `finished_at` の最大(エポックミリ秒)を、
    UTC ミリ秒の文字列に。なければ `None`。

    浮動小数の秒に直さない(ミリ秒の端数がずれるため)。
    """
    if epoch_millis is None:
        return None
    try:
        return format_instant(_EPOCH + timedelta(milliseconds=epoch_millis))
    except OverflowError:
        return None


def delete_job_of[T](source_status: SourceStatus | None, latest_delete: T | None) -> T | None:
    """ソースが `deleting` のときだけ、最新の `source_delete` ジョブ。

    `active` のソースは常に `None`。
    """
    return latest_delete if source_status is SourceStatus.DELETING else None

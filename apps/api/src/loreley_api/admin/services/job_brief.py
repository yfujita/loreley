"""`JobBrief` の項目の組み立て(EP-01・02・09・10 で共有する)。"""

import dataclasses
from typing import Any

from loreley_api.admin.derivation.job_view import JobBriefView
from loreley_api.admin.derivation.stalled import is_cancellable
from loreley_api.admin.schemas.common import JobBrief


def brief_fields(brief: JobBriefView, stalled: bool | None) -> dict[str, Any]:
    """`JobBrief` の項目(`stalled` が `null` のとき `cancellable` は `false`)。

    `JobListItem` などの、`JobBrief` を継承した DTO に展開して使う。
    """
    return {
        **dataclasses.asdict(brief),
        "stalled": stalled,
        "cancellable": is_cancellable(brief.job_type, brief.status, stalled),
    }


def job_brief(brief: JobBriefView, stalled: bool | None) -> JobBrief:
    return JobBrief(**brief_fields(brief, stalled))

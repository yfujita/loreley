"""死活確認(EP-13)1 件の結果。

`infrastructure.opensearch` と `infrastructure.probes` は互いに依存しないので、共有する結果の型を
ここに置く(AAM-P-12)。`not_configured`(未設定)は確認をしないので、この型には含めない。
"""

from dataclasses import dataclass
from typing import Literal

ProbeState = Literal["normal", "abnormal", "undetermined"]
ProbeReason = Literal[
    "connection_refused",
    "name_not_resolved",
    "unexpected_status",
    # 返す確認はない(`web` を HTTP の確認に置き換えた)。EP-13 の `reason` の列挙(OpenAPI)を
    # 変えないために残している。
    "missing",
    "timeout",
    "connection_error",
]


@dataclass(frozen=True)
class ProbeOutcome:
    state: ProbeState
    # `abnormal`・`undetermined` のときの診断用の理由。`normal` は `None`。
    reason: ProbeReason | None = None

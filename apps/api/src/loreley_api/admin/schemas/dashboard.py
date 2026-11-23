"""EP-13 の DTO(B 8.1)。"""

from loreley_api.admin.base.codes import ComponentId, ComponentState
from loreley_api.admin.schemas.common import ResponseModel
from loreley_api.common.probe_outcome import ProbeReason


class ComponentStatus(ResponseModel):
    id: ComponentId
    state: ComponentState
    # `abnormal`・`undetermined` のときの診断用の理由。`normal`・`not_configured` は `null`。
    reason: ProbeReason | None
    # そのコンポーネントの確認が終わった時刻。
    checked_at: str


class DashboardResponse(ResponseModel):
    """固定の順(`ComponentId` の宣言順)で常に 8 件。

    各コンポーネントの失敗は `components[].state` で表すので、`unavailable` もエラー応答もない。
    """

    # 全コンポーネントの確認が終わり、応答を組み立てた時刻(各 `components[].checked_at` 以上)。
    checked_at: str
    components: list[ComponentStatus]

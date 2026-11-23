"""EP-14 の DTO(B 8.2)。"""

from loreley_api.admin.schemas.common import ResponseModel


class MetaResponse(ResponseModel):
    """`api` の設定(環境変数)に由来する情報。未設定は `null`。"""

    cron_timezone: str | None
    dashboards_url: str | None

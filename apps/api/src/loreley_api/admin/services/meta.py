"""メタ情報(EP-14)。`api` の設定(環境変数)だけで応答し、他のコンポーネントを呼ばない。

設定の値は、`admin` 直下の組み立て(`dependencies.py`)が `AdminSettings` から取り出して渡す
(`services` は `admin` 直下を import しない。R4)。
"""

from loreley_api.admin.schemas.meta import MetaResponse


class MetaService:
    def __init__(self, *, cron_timezone: str | None, dashboards_url: str | None) -> None:
        self._cron_timezone = cron_timezone
        self._dashboards_url = dashboards_url

    async def get_meta(self) -> MetaResponse:
        return MetaResponse(cron_timezone=self._cron_timezone, dashboards_url=self._dashboards_url)

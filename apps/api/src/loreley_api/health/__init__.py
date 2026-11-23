"""ヘルスチェックの機能パッケージ。`GET /healthz` だけを持つ。

admin・search と同じ「機能パッケージ」の形(`common` と `fastapi` だけに依存し、`server` から
は import されない)で、`main` が組み立てて `create_app` に渡す。
入口は `create_health_router()` と `HEALTH_PATH`。
"""

from loreley_api.health.router import HEALTH_PATH, create_health_router

__all__ = ["HEALTH_PATH", "create_health_router"]

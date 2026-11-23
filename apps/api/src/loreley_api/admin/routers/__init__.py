"""EP の受け口(D 4.3)。EP を実装するフェーズで、ファイルごとのルーターをここで束ねる。

ルーターには `AdminDependencies` ではなく、必要なサービスを渡す。`admin.routers` は `admin` 直下
(`dependencies.py`)を import できない(R4。import すると admin → routers → admin の循環になる)。
"""

from fastapi import APIRouter


def create_admin_router() -> APIRouter:
    router = APIRouter()
    return router

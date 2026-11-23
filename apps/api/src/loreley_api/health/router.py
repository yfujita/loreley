from fastapi import APIRouter

HEALTH_PATH = "/healthz"


def create_health_router() -> APIRouter:
    """`api` 自身のヘルスチェック(契約外。A 6章)。

    何も呼ばない(OpenSearch・Crawler・Indexer への到達性は見ない)ので、スレッドも使わない
    `async def`。アプリケーションが受け付けを始めていれば 200 を返す。
    """
    router = APIRouter()

    @router.get(HEALTH_PATH)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return router

"""エントリポイント: 設定の読み込み、ログ設定、機能の組み立て、起動(Composition Root)。

機能パッケージを知っているのは、`server` ではなくこのモジュールだけ。機能を足すときは、
`build_app` でその機能を作って `create_app` の口(`routers` または `mounts`)に渡す。

uvicorn は単一プロセス(ワーカー数 1)で動かす。
起動: `python -m loreley_api.main`
"""

import uvicorn
from fastapi import FastAPI

from loreley_api.common.logging_setup import configure_logging
from loreley_api.config import load_settings
from loreley_api.health import HEALTH_PATH, create_health_router
from loreley_api.server import create_app


def build_app() -> FastAPI:
    """外部に接続せずに、アプリを組み立てる。

    `/healthz` は、コンテナの確認が数秒おきに呼ぶため、アクセスログを DEBUG にする。
    """
    return create_app(
        routers=[create_health_router()],
        debug_access_log_paths={HEALTH_PATH},
    )


def main() -> None:
    # 設定が不正なら `ConfigError`(値を含まない)で、ここで異常終了する。
    settings = load_settings()
    configure_logging(level=settings.log_level)
    app = build_app()
    # アプリケーションのオブジェクトを渡すので単一プロセス(ワーカーは増やさない)。
    # ログの設定は `configure_logging` に任せ(`log_config=None`)、uvicorn のアクセスログは
    # ID を含む実際のパスを出すため無効にする(自前のアクセスログを使う)。
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()

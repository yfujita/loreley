"""外側の `FastAPI` アプリ(A 2.1・2.2・5.1・5.4。module 4.2)。

機能パッケージ(`health`・将来の `admin` など)は import しない。`main` が機能を組み立て、
次の 2 つの口から載せる。
- `routers`: 外側に直接載せるルーター(`/healthz` のようなルート直下の機能)。
- `mounts`: 独立した `FastAPI` アプリとしてマウントするサブアプリ(admin のようなもの。BAPI-P-9)。

サブアプリには、共通の例外ハンドラと middleware を設置する。サブアプリは自分の例外ハンドラ・
最外殻の Starlette を持つので、外側の設置は届かない(AAM-P-23)。
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI
from starlette.types import Lifespan

from loreley_api.common.http import install_common_http


@dataclass(frozen=True)
class SubAppMount:
    """`prefix`(例 `/api/admin/v1`。先頭は `/`、末尾は `/` なし)にマウントするサブアプリ。

    サブアプリ側では `install_common_http` を呼ばない(`create_app` が設置する。二重になる)。
    また `create_app` は、`app.router.redirect_slashes` を False にする(副作用)。
    """

    prefix: str
    app: FastAPI


def create_app(
    *,
    routers: Sequence[APIRouter] = (),
    mounts: Sequence[SubAppMount] = (),
    debug_access_log_paths: Collection[str] = (),
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """外側のアプリを作る。

    `lifespan` は、機能が持つ資源(クライアントなど)の開始・終了のために `main` が渡す。
    マウントしたサブアプリ自身の `lifespan` は、Starlette では実行されないので、ここに渡す。
    `debug_access_log_paths` は、アクセスログを DEBUG にするルートのテンプレート(`/healthz`)。

    マウントするサブアプリ側では `install_common_http` を呼ばない(ここで設置するので、二重になる)。
    また、各 `mount.app.router.redirect_slashes` を False にする副作用がある(A 5.1)。
    """
    # 対話型ドキュメントと OpenAPI は公開しない(A 5.4)。末尾スラッシュはリダイレクトしない(A 5.1)。
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
        lifespan=lifespan,
    )
    for router in routers:
        app.include_router(router)
    for mount in mounts:
        # サブアプリの作り方に関わらず、末尾スラッシュのリダイレクトはしない(A 5.1)。
        mount.app.router.redirect_slashes = False
        # アクセスログは、サブアプリの処理が終わった後に、外側が 1 回だけ出す(middleware.py)。
        install_common_http(mount.app, log_access=False)
        app.mount(mount.prefix, mount.app)
    install_common_http(app, debug_access_log_paths=debug_access_log_paths)
    return app

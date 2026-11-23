"""admin の依存(組み立て済みの部品)の入れ物(D 4.1)。

`main.py` が作って `create_admin_app` に渡す。ルーターは、この入れ物を受け取らない。`app.py` が
必要なサービスを個別にルーターへ渡す(D 4.3 の `create_admin_router(deps)` は、D 6章の許可表と
循環するため。0004 申し送り 1)。サービスは、EP を実装するときにここへ足す。
"""

from dataclasses import dataclass

from loreley_api.admin.settings import AdminSettings
from loreley_api.common.clock import Clock
from loreley_api.common.concurrency import BlockingRunner


@dataclass(frozen=True)
class AdminDependencies:
    settings: AdminSettings
    clock: Clock
    runner: BlockingRunner

"""Admin API(機能パッケージ。FastAPI のサブアプリ。D 4章)。

`main` が、Reader・設定・時計・`BlockingRunner` から `build_admin_dependencies` で
`AdminDependencies` を作り、`create_admin_app(deps)` を `/api/admin/v1` にマウントする。
"""

from loreley_api.admin.app import ADMIN_API_PREFIX, create_admin_app
from loreley_api.admin.dependencies import (
    AdminDependencies,
    AdminProbes,
    AdminReaders,
    build_admin_dependencies,
)
from loreley_api.admin.settings import AdminSettings

__all__ = [
    "ADMIN_API_PREFIX",
    "AdminDependencies",
    "AdminProbes",
    "AdminReaders",
    "AdminSettings",
    "build_admin_dependencies",
    "create_admin_app",
]

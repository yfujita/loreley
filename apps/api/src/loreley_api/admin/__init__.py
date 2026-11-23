"""Admin API(機能パッケージ。FastAPI のサブアプリ。D 4章)。

`main` が、設定(`AdminSettings`)・時計・`BlockingRunner` から `AdminDependencies` を作り、
`create_admin_app(deps)` を `/api/admin/v1` にマウントする。
"""

from loreley_api.admin.app import create_admin_app
from loreley_api.admin.dependencies import AdminDependencies
from loreley_api.admin.settings import AdminSettings

__all__ = ["AdminDependencies", "AdminSettings", "create_admin_app"]

"""Admin API からの HTTP の受け口(module 4.1)。形式の検証と受け渡しだけを行う。

入口は `create_app(ApiDependencies(...))`。`jobs`・`sources` の入口だけを呼ぶ(R4)。
"""

from loreley_crawler.api.app import create_app
from loreley_crawler.api.dependencies import ApiDependencies

__all__ = ["ApiDependencies", "create_app"]

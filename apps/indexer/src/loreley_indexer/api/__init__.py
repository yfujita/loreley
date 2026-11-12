"""HTTP の窓口(module 4.1)。Crawler からの 8 つの API と `/healthz`。

形式の検証、共通のエラー形式への変換、応答の整形だけを行う。受理条件の判定や書き込みの判断は、
担当機能(`crawl_runs`、`documents`)が行う(R4)。infrastructure は直接使わない。
"""

from loreley_indexer.api.app import create_api_app
from loreley_indexer.api.config import ApiConfig
from loreley_indexer.api.dependencies import ApiDependencies

__all__ = ["ApiConfig", "ApiDependencies", "create_api_app"]

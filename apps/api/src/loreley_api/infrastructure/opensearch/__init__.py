"""OpenSearch の読み取り専用アクセス(D 4.8)。

入口は、設定の型(`config.py` がこの入口だけを import する)。Reader・読み取り用のラッパーは
未実装で、実装するときにここへ足す。
"""

from loreley_api.infrastructure.opensearch.config import IndexNames, OpenSearchConnectionConfig

__all__ = ["IndexNames", "OpenSearchConnectionConfig"]

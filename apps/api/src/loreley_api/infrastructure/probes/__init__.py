"""`GET /healthz` のプローブと、`web` のファイル確認(D 4.10)。

入口は、設定の型(`config.py` がこの入口だけを import する)。プローブ本体は未実装。
"""

from loreley_api.infrastructure.probes.config import HttpProbeConfig

__all__ = ["HttpProbeConfig"]

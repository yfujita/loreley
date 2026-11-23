"""外側のアプリ(エントリ層)。機能パッケージを import せず、機能を載せる口だけを持つ。"""

from loreley_api.server.app import SubAppMount, create_app

__all__ = ["SubAppMount", "create_app"]

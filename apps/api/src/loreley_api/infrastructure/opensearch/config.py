from dataclasses import dataclass, field


@dataclass(frozen=True)
class OpenSearchConnectionConfig:
    """OpenSearch への接続設定(C 3.7・7.2)。値の検証は `config.py` が済ませている。"""

    url: str
    username: str | None
    # `repr` に出さない(ログ・例外のメッセージへの混入を防ぐ)。
    password: str | None = field(repr=False)
    verify_certs: bool
    ca_certs_path: str | None
    # 読み取り用クライアントの 1 リクエストのタイムアウト(接続・読み取りそれぞれ)。
    request_timeout_seconds: float
    max_retries: int
    # プローブ用クライアント(`cluster.health` だけ)のタイムアウト。再試行はしない。
    probe_timeout_seconds: float


@dataclass(frozen=True)
class IndexNames:
    """読む索引の名前。`search` は、検索インデックスの**エイリアス**(実体名ではない。I-90)。"""

    sources: str
    jobs: str
    deletions: str
    search: str

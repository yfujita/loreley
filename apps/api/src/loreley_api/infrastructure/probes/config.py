from dataclasses import dataclass


@dataclass(frozen=True)
class HttpProbeConfig:
    """HTTP プローブの設定(C 6.1)。確認先の URL は呼び出し側(`services`)が渡す。"""

    # 確認 1 件のタイムアウト(接続と読み取りの合計)。
    timeout_seconds: float

from enum import StrEnum


class DeletionOutcome(StrEnum):
    """削除結果 1 件の処理(`DeletionProcessor.process`)の結末。"""

    FINISHED = "finished"  # 終端状態を書いた
    CLOSED = "closed"  # 自分の結果が終端状態・404。何も書き換えずに止まった(9.7、9.8)
    WAITING = "waiting"  # 先行する削除が終端状態になるのを待つ(判定しない。9.7 順1)
    NOT_QUEUED = "not_queued"  # 終了通知を受理していない(待ち行列にない)
    STOPPED = "stopped"  # 停止が要請された。結果は `running` のまま(再起動時の整理で `failed`)

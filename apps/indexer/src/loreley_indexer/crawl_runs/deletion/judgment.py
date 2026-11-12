"""削除判定の純粋な部分(arch 9.2、9.3、9.7 の順4・5)。OpenSearch には触れない。"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from loreley_indexer.crawl_runs.lifecycle import DeletionResultRecord

# TTL は範囲を検証しない(確定。9.13(9))ため、巨大な値で `timedelta` や日時の計算が
# 溢れて例外にならないよう、約 100 年に丸める。100 年を超える TTL は「何も期限切れにならない」
# のと同じで、丸めても判定は変わらない。負の値も同じ幅で丸める(未来の時刻を基準にする)。
MAX_TTL_SECONDS = 100 * 366 * 24 * 60 * 60


def ttl_cutoff(now: datetime, ttl_seconds: int) -> datetime:
    """`last_seen_at + TTL < now` を、`last_seen_at < cutoff` と書けるようにした `cutoff`。

    判定時刻・再確認時刻のどちらにも使う(arch 9.8: `cutoff = 判定時刻 - TTL`)。
    """
    clamped = max(-MAX_TTL_SECONDS, min(ttl_seconds, MAX_TTL_SECONDS))
    return now - timedelta(seconds=clamped)


def is_expired(last_seen_at: datetime, *, now: datetime, ttl_seconds: int) -> bool:
    return last_seen_at < ttl_cutoff(now, ttl_seconds)


def passes_ratio_rule(
    *, target_count: int, denominator: int, min_delete_count: int, ratio_threshold: float
) -> bool:
    """割合ルールの判定 1・2(arch 9.3)。強制削除モードは呼び出し側が、この判定を行わない。

    1. T が最小件数以下なら、率に関わらず削除する。
    2. そうでなければ、T ÷ D がしきい値以下なら削除する。超えるなら削除しない。

    範囲外の値(しきい値が負・100% 以上、最小件数が負など)は検証せず、そのまま使う(9.13(9))。
    しきい値が NaN のとき `T ÷ D <= NaN` は偽で、削除しない側に倒れる。
    """
    if target_count <= min_delete_count:
        return True
    if denominator <= 0:
        return False  # T > 0 のときは D ≧ T > 0(T > D のガードの後)。防御的に削除しない側へ。
    return target_count / denominator <= ratio_threshold


@dataclass(frozen=True)
class Measurements:
    """判定・実行の数値(arch 9.4: `n_seen`、`e_missing`、T、D)。値のないものは記録しない。"""

    n_seen: int | None = None
    e_missing: int | None = None
    target_count: int | None = None
    denominator: int | None = None

    def recorded_in(self, record: DeletionResultRecord) -> DeletionResultRecord:
        return replace(
            record,
            n_seen=self.n_seen if self.n_seen is not None else record.n_seen,
            e_missing=self.e_missing if self.e_missing is not None else record.e_missing,
            target_count=(
                self.target_count if self.target_count is not None else record.target_count
            ),
            denominator=self.denominator if self.denominator is not None else record.denominator,
        )


def progress_update(
    measurements: Measurements, deleted_count: int | None = None
) -> Callable[[DeletionResultRecord], DeletionResultRecord]:
    """判定の数値と、ここまでの `deleted_count` を記録する更新(終端遷移・進捗の書き込みで使う)。

    書き込みが 409 になって読み直したときも、最新の記録に対して適用し直せるよう、関数で渡す。
    記録済みの `deleted_count` は減らさない(再実行の判定で、削除済みの件数を消さないため)。
    """

    def update(record: DeletionResultRecord) -> DeletionResultRecord:
        recorded = measurements.recorded_in(record)
        if deleted_count is None:
            return recorded
        return replace(recorded, deleted_count=max(deleted_count, record.deleted_count or 0))

    return update

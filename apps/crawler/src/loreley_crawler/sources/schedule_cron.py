"""定期起動の cron 式(architecture 3.2・4.3。設定項目 `schedule_cron`)。

標準の 5 項目(分 時 日 月 曜日)だけを受け付ける。解釈は cronsim(5 項目の厳密なパーサ。
zoneinfo に対応)に任せ、ライブラリの例外は `InvalidScheduleCron` に写す(想定外の例外を
HTTP の 500 にしないため、検証側の `is_valid_schedule_cron` は例外を出さない)。

cronsim が許す次のものは、そのまま受け付ける(止めない): 曜日・月の英語名(`MON`・`JAN`)、
`L`・`LW`・`#`。夏時間のある TZ での存在しない時刻(春)は cronsim に従う。2 回ある時刻(秋)は、
起点より前の瞬間を返さないように、`next_fire_time` が補正する。
"""

import re
from datetime import UTC, datetime, tzinfo

from cronsim import CronSim, CronSimError

# 5 項目の式は通常 50 文字に収まる(全項目を列挙しても 300 文字弱)。リクエスト本文の上限
# (10 MiB)いっぱいの文字列を、パーサに渡さないための余裕をみた上限。
SCHEDULE_CRON_MAX_LENGTH = 512

# 空白 1 つで区切った、空白を含まない 5 項目。cronsim は 6 項目(秒つき)・`@daily` などの別名・
# 前後の空白や複数の空白も受け付けるので、「標準の 5 項目」はここで絞る。
_FIVE_FIELDS = re.compile(r"\S+( \S+){4}")

# 検証だけに使う起点。合う時刻が先にあるかを確かめるだけなので、固定の値にする(現在時刻に
# 依存させない)。
_VALIDATION_ORIGIN = datetime(2000, 1, 1, tzinfo=UTC)


class InvalidScheduleCron(ValueError):
    """5 項目の cron 式として不正、または合う時刻が(探索の範囲に)ない。値は載せない。"""


def next_fire_time(expression: str, *, after: datetime, zone: tzinfo) -> datetime:
    """`after`(タイムゾーン付き)より後で最初に `expression` に合う時刻(`zone` の暦で解釈)。

    `after` ちょうどの時刻は含まない。返す値は `zone` のタイムゾーン付きなので、現在時刻との
    比較は瞬間(UTC)として行える。
    """
    if len(expression) > SCHEDULE_CRON_MAX_LENGTH or _FIVE_FIELDS.fullmatch(expression) is None:
        raise InvalidScheduleCron("not a five-field cron expression")
    try:
        fires = CronSim(expression, after.astimezone(zone))
        after_instant = after.astimezone(UTC)
        fire = next(fires)
        # 夏時間が終わる日の「2 回ある時刻」(例 `30 1 * * *`)で、cronsim は 2 回目の時間帯にある
        # 起点に対して、1 回目の時刻(起点より前の瞬間)を返すことがある。「`after` より後」を守る
        # ため、瞬間(UTC)で比べて起点以前のものは捨てる(同じ時刻が繰り返し起動するのを防ぐ)。
        while fire.astimezone(UTC) <= after_instant:
            fire = next(fires)
        return fire
    except (CronSimError, StopIteration):
        raise InvalidScheduleCron("invalid cron expression") from None


def is_valid_schedule_cron(expression: str) -> bool:
    try:
        next_fire_time(expression, after=_VALIDATION_ORIGIN, zone=UTC)
    except InvalidScheduleCron:
        return False
    except Exception:
        # 入力は利用者の文字列だけで、起点は固定。ライブラリが想定外の例外を出しても、
        # 入力の不正として扱い、検証の呼び出し元(HTTP の応答)を 500 にしない。
        return False
    return True

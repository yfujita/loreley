"""`crawler`・`indexer`・任意コンポーネントの `GET` による死活確認(C 6.1。D 4.10)。

- **メソッドは `GET` だけ**。確認先は、呼び出し側(`services.dashboard`)が設定(環境変数)から得た
  URL だけを渡す。リクエストの入力から確認先が決まる経路はない(SSRF の予防。C 6.4)。
- **リダイレクトに従わない**(`redirect=False`)。3xx は 2xx 以外として `unexpected_status`。
- **再送しない**(`retries=False`。A 5.6)。確認 1 件の接続と読み取りの合計を
  `Timeout(total=…)` に収める。
- **本文は読まない**(`preload_content=False`。状態行だけ見て接続を閉じる)。応答が大きくても
  影響しない。
- 接続は使い回さない(`Connection: close`)。確認の間隔(30 秒)が長く、使い回した接続が相手に
  閉じられていると、本当は動いているのに失敗に見えるため。

ログには、固定の結果の区分(`state`・`reason`)と例外のクラス名だけを出す。URL・ホスト名・例外の
メッセージは出さない(R11)。urllib3 のロガーは `logging_setup` が ERROR 以上に固定する。
"""

import logging

import urllib3

from loreley_api.common.probe_outcome import ProbeOutcome
from loreley_api.infrastructure.probes import classification
from loreley_api.infrastructure.probes.config import HttpProbeConfig

logger = logging.getLogger(__name__)

# `probe` の枠の上限(C 8.1)に合わせる。接続は使い回さないので、同時に開く接続の数の上限になる。
_POOL_MAXSIZE = 8


class HttpHealthProbe:
    def __init__(self, config: HttpProbeConfig) -> None:
        self._timeout = urllib3.Timeout(total=config.timeout_seconds)
        self._pool = urllib3.PoolManager(num_pools=4, maxsize=_POOL_MAXSIZE)

    def close(self) -> None:
        self._pool.clear()

    def check(self, url: str) -> ProbeOutcome:
        outcome = self._check(url)
        logger.debug(
            "health probe finished: state=%s reason=%s", outcome.state, outcome.reason or "-"
        )
        return outcome

    def _check(self, url: str) -> ProbeOutcome:
        try:
            response = self._pool.request(
                "GET",
                url,
                headers={"Connection": "close"},
                timeout=self._timeout,
                retries=False,
                redirect=False,
                preload_content=False,
            )
            try:
                return classification.classify_status(response.status)
            finally:
                # 未読の本文が残る接続を使い回させない。
                response.close()
                response.release_conn()
        except Exception as error:
            # 確認は例外を漏らさない(想定外の例外も「判定不能」にする)。
            logger.debug("health probe failed: error=%s", type(error).__name__)
            return classification.classify_exception(error)

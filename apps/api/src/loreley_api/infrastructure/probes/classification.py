"""HTTP の確認結果の分類(C 6.2 の 1 つ目の表。D 4.10)。

urllib3 2.x の継承(`NameResolutionError` は `NewConnectionError` の子、`NewConnectionError` は
`ConnectTimeoutError` の子)に合わせ、**狭いほうから順に**判定する。

`str(error)` は URL・ホスト名を含みうるので、返り値にもログにも載せない(R11)。
"""

from urllib3.exceptions import (
    ConnectTimeoutError,
    NameResolutionError,
    NewConnectionError,
    ReadTimeoutError,
)

from loreley_api.common.probe_outcome import ProbeOutcome

NORMAL = ProbeOutcome("normal")
UNEXPECTED_STATUS = ProbeOutcome("abnormal", "unexpected_status")
NAME_NOT_RESOLVED = ProbeOutcome("abnormal", "name_not_resolved")
CONNECTION_REFUSED = ProbeOutcome("abnormal", "connection_refused")
TIMEOUT = ProbeOutcome("undetermined", "timeout")
CONNECTION_ERROR = ProbeOutcome("undetermined", "connection_error")


def classify_status(status: int) -> ProbeOutcome:
    """2xx だけが正常。3xx(リダイレクトは追わない)・4xx・5xx(起動前の 503 を含む)は異常。"""
    is_success = 200 <= status < 300
    return NORMAL if is_success else UNEXPECTED_STATUS


def classify_exception(error: Exception) -> ProbeOutcome:
    """確認の途中で起きた例外を分類する。

    `urllib3.exceptions.HTTPError` の他の型(`ProtocolError`・`SSLError` ほか)と、想定外の例外は、
    確認自体が失敗して分からないので「判定不能(`connection_error`)」にする。
    """
    if isinstance(error, NameResolutionError):
        return NAME_NOT_RESOLVED
    if isinstance(error, NewConnectionError):
        return CONNECTION_REFUSED
    if isinstance(error, ConnectTimeoutError | ReadTimeoutError):
        return TIMEOUT
    return CONNECTION_ERROR

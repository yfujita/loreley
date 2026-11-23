from loreley_api.admin.base.codes import UnavailableReason
from loreley_api.common.results import Failed


def reason_of(failed: Failed) -> UnavailableReason:
    """失敗した読み取りの理由コード。**タイムアウトを優先する**(遅いのか止まっているのかを区別する)。"""
    if failed.kind == "timeout":
        return UnavailableReason.TIMEOUT
    if failed.target == "store":
        return UnavailableReason.STORE_UNAVAILABLE
    return UnavailableReason.SEARCH_INDEX_UNAVAILABLE

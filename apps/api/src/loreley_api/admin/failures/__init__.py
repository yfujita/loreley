"""部分失敗の理由コードと `unavailable` の組み立て(C 5.8・8.6。D 4.7)。"""

from loreley_api.admin.failures.reasons import reason_of
from loreley_api.admin.failures.unavailable import row_unavailable, top_level_unavailable

__all__ = ["reason_of", "row_unavailable", "top_level_unavailable"]

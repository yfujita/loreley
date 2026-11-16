"""ログに出す識別子の整形(R11: 切り詰めと制御文字のエスケープを通す)。"""

from loreley_crawler.common.display_text import format_display_text

LOG_ID_MAX_CHARS = 200


def loggable_id(value: str) -> str:
    return format_display_text(value, max_chars=LOG_ID_MAX_CHARS)

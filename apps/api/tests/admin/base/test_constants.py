"""`admin.base` と `infrastructure.opensearch` が別々に持つ、同じ意味の上限が一致していること。

`admin` は `infrastructure` に依存しない葉(`admin.base`)に値を持つので(D 6章)、同じ値が 2 か所に
ある。片方だけ変えると、窓を超える要求が OpenSearch に届いて失敗するなどの食い違いが出る。
"""

from loreley_api.admin.base import constants as admin_constants
from loreley_api.common.http.body import MAX_REQUEST_BODY_BYTES
from loreley_api.infrastructure.crawler_client.parsing import RESPONSE_MAX_BYTES
from loreley_api.infrastructure.opensearch import ports

# Crawler が登録・更新の応答に足す項目(`status`・`updated_at` など)に十分な余裕。
RESPONSE_HEADROOM_BYTES = 16 * 1024


def test_the_page_window_matches_the_max_result_window() -> None:
    assert admin_constants.PAGE_WINDOW_LIMIT == ports.MAX_RESULT_WINDOW


def test_the_largest_items_per_page_matches_the_infrastructure_limit() -> None:
    assert max(admin_constants.ITEMS_PER_PAGE_CHOICES) == ports.MAX_ITEMS_PER_PAGE


def test_the_sources_fetch_limit_matches_the_max_sources() -> None:
    assert admin_constants.SOURCES_FETCH_LIMIT == ports.MAX_SOURCES


def test_the_existence_lookup_limit_matches_the_max_existence_ids() -> None:
    assert admin_constants.EXISTENCE_LOOKUP_LIMIT == ports.MAX_EXISTENCE_IDS


def test_the_crawler_response_limits_match_between_admin_and_infrastructure() -> None:
    assert admin_constants.CRAWLER_RESPONSE_MAX_BYTES == RESPONSE_MAX_BYTES


def test_the_crawler_response_limit_leaves_room_over_the_request_body_limit() -> None:
    """上限いっぱいの設定が保存できたのに、応答が上限を超えて 502 になるのを防ぐ。"""
    assert (
        admin_constants.CRAWLER_RESPONSE_MAX_BYTES
        >= MAX_REQUEST_BODY_BYTES + RESPONSE_HEADROOM_BYTES
    )

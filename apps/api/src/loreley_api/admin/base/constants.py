"""固定の上限と既定(C 9章)。環境変数にしない(仮値で、実測して見直す)。"""

# ページの窓: `page * items_per_page` がこれを超える要求は 400。OpenSearch の `max_result_window`
# の既定に合わせた(B 2.1)。
PAGE_WINDOW_LIMIT = 10_000
ITEMS_PER_PAGE_CHOICES = (25, 50, 100)
DEFAULT_ITEMS_PER_PAGE = 25

# EP-11 の `existence`(検索インデックスの一括検索)で 1 回に取得する ID の上限。
EXISTENCE_LOOKUP_LIMIT = 100

# EP-12 が返すインデックスの上限(超過は切り詰め)。
CLUSTER_INDEX_LIMIT = 1_000

# `loreley-sources` の全件取得の上限(超過は 503)。
SOURCES_FETCH_LIMIT = 10_000

# Crawler の応答本文の上限(超過は 502 `crawler_error`)。
CRAWLER_RESPONSE_MAX_BYTES = 1024 * 1024

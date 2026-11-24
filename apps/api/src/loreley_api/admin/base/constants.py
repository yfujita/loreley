"""固定の上限と既定(C 9章)。環境変数にしない(仮値で、実測して見直す)。"""

import re

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

# Crawler の応答本文の上限(超過は 502 `crawler_error`)。登録・更新の応答は、受け取った設定に
# `status`・`updated_at` などを足して返す。リクエスト本文の上限(1 MiB)に近い設定が保存できたのに
# 応答が上限を超えて 502 になる(保存は成功しているのにエラーが返る)ことを、通常の設定では避けるため
# 2 MiB にする。非 ASCII だけの設定は JSON の `\uXXXX` 表記で膨らみうるので、窓が完全にゼロになる
# わけではない(1 MiB 級の設定自体が非現実的なので許容する)。
CRAWLER_RESPONSE_MAX_BYTES = 2 * 1024 * 1024

# `source_id`(パス・登録の本文で共通): 半角英数字で始まり、半角英数字・`.`・`_`・`-` だけの
# 256 文字以内(B 2.12。Crawler と同じ規則)。ASCII だけなので文字数 = バイト数。
SOURCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}")

"""`crawl` の確認点の組み合わせ。"""

from loreley_crawler.jobs import Check

# Indexer を呼ばない処理(列挙・取得・Store 層の書き込みの待ち)で通す確認点。いずれも I/O のない
# 確認(メモリ上の所有状態と取り消し要求)で、文書の区切りごとに通しても軽い。メンテナンス
# フラグは Store 層を読むので、Indexer への要請の前(`Check.ALL`)にだけ確認する。
LOCAL_CHECKS = Check.OWNERSHIP | Check.CANCELLATION

# 確認しない。終了通知 `failed`・`cancelled`(所有・取り消し・メンテナンスの確認の対象外。
# architecture 5.7・7.9)と、そのリトライの待ちに使う。
NO_CHECKS = Check(0)

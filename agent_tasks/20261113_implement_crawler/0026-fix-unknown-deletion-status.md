# 0026 PR レビュー指摘への対応: 未知の削除ステータスを confirmed と判定してしまう

日付: 2026-11-16 / 実施・記録: メインエージェント(サブエージェントは使っていない)

## 1. 指摘(ユーザーが貼ったレビュー指摘。[P2])

`crawl/status_polling.py` は `reply.status != "running"` なら `confirmed` にする。`infrastructure/indexer_client/parsing.py` は `status` を単なる文字列として受け取るため、Indexer が契約外の値(例 `processing`)を返しても `confirmed` になる。修正案: 応答の解析で既知の `status` を検証し、未知の値を `MalformedResponseError` にする(「`running` 以外はすべて終端」という仕様は維持)。

## 2. 確認と対応

- 指摘は正しい(再現: 契約外の `status` を返す応答が `CrawlStatus` になり、`running` 以外なので `confirmed`)。Indexer 側の定義(`apps/indexer/.../lifecycle/records.py` の `DeletionStatus`)は 6 値で、indexer-api 4.5 と一致(名前の一覧は案)
- 修正: `parsing.py` に `KNOWN_DELETION_STATUSES`(6 値)を置き、`parse_status` で未知の値を `MalformedResponseError`(呼び出し側へは `IndexerRejected(200, malformed_response)`)にした。`status_polling.py` は変更なし(`running` 以外は終端のまま)。契約違反の応答は、ポーリングの失敗(404 以外)として数えられ、連続が規定の回数に達すると `unconfirmed`
- テスト: 契約外の値(`processing`・`Running`・空文字)が契約違反になること、契約の 6 値が受理されること、契約違反の連続が `unconfirmed` になること(ポーリング)。検証を外す変異で 3 件が落ちることを確認し、元に戻した(`cp -f`。変異の残りなし)
- 設計書: architecture v0.4 の 7.6 に「契約にない `status` の扱い」を追記(実装で決めた内容)。その場で更新

## 3. 検証

- `uv run pytest -q`: 3331 passed・3 skipped(3321 から +10)。`ruff check`・`ruff format --check` 成功

## 4. 未対応・注意

- Indexer が `status` に値を足したときは、Crawler の一覧(`KNOWN_DELETION_STATUSES`)の更新が要る(足し忘れは `unconfirmed` になり、削除自体は止まらない=安全側)
- レビューは省略(小さな修正で、変異で検出を確認)

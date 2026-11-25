# 0009 P5: 最終確認と文書

日付: 2026-11-25
担当: メインエージェント(最終確認・修正)、document-writer(README・結果文書の本文)

## 実施内容

- `tests/integration/api/README.md` と `docs/v0.x/test-results/admin-api-integration.md` を document-writer が作成(0004〜0008 の観測値・判断・発見事項に基づく。確認できなかった点は「未記録」と記載)。最終確認の欄(4.6)と冒頭の状態行はメインエージェントが記入
- `deploy/compose/README.md` の古い記述を更新(api の起動確認は IT で実施した旨、HO-45 の実機確認は AIT-90・91 で実施した旨。`web` が mount なしで `abnormal` になることは実機未確認のまま)
- 最終確認(クリーンな状態から、`--keep` なし):
  - `apps/api` 単体テスト 3423 passed、ruff OK
  - 既存 Crawler IT 14 passed、Indexer IT 40 passed(`compose.yaml` 変更後の退行なし)
  - api IT を 6 回実行(履歴は結果文書 4.6)
- **api IT の不安定さが 2 件見つかった**:
  1. 2 回目の失敗(AIT-60)は、実行中のホストのスリープ(Crawler ログが約 1 時間 38 分途切れ、`lock_lost`/`lease_expired`)と判断。アプリ・テストの不具合ではない。README に「IT 実行中はホストをスリープさせない」と追記し、以降は `caffeinate -i` を付けて実行した
  2. 4 回目の失敗(AIT-20)は、テストの待ち不足(EP-02 で `last_crawl` は `succeeded` だが `last_completed_at` がまだ `null`)。`test_20_crawl.py` の待ちの条件に `last_completed_at`(ジョブの `finished_at` との一致)と文書数を加えた(EP-02・EP-01 の両方)。アサートの期待値は変えていない。アプリの不具合ではなく、設計の AAA-P-6(検索の反映遅れ最大約 1 秒)の範囲内
- 修正後のコードで、クリーンな状態から 2 回連続で全 23 件成功(354.1 秒・357.8 秒)

## 変更したファイル

`tests/integration/api/test_20_crawl.py`(待ちの条件)、`tests/integration/api/README.md`(新規。スリープの注意を追記)、`docs/v0.x/test-results/admin-api-integration.md`(新規)、`deploy/compose/README.md`(更新)

## 判断・設計上の理由

- 4 回目の失敗をテスト側の待ち不足と判断した根拠: ジョブ詳細(ID 指定)と `last_crawl` は即時に見えるが、`last_completed_at`・文書数は検索で読むため遅れうる(P3a・P3b で観測した反映遅れと同じ種類)。待ちの条件に加えるだけで期待値は動かしていない
- 他の `wait_for_source_detail`・`wait_for_source_row` の使用箇所は、確認する値と待ちの条件が揃っていること(AIT-21 などは文書数のみを確認)を目視で確認した。同種の不安定さは 5・6 回目の 2 回連続成功では出ていないが、確率的な事象のため「完全に消えた」とは断定できない

## 未対応事項・次にやること

- 次: レビューフェーズ(code-reviewer・test-reviewer・document-reviewer を並列)。特に test-reviewer には、反映遅れに対する待ちの網羅(同種の不安定さが他に残っていないか)と、スリープ・窓への依存を見てもらう
- 結果文書の 9 章に設計書追従改訂の申し送り(api-base-design 9.2 の HO-34・35・40・41・43・44 の状態更新と HO-45 の補足。HO-44 は `docker compose config` での確認止まり)
- 据え置き: `apps/api/Dockerfile` 11 行目の古いコメント、shellcheck 未実施

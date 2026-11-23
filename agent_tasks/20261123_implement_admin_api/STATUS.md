# タスク状態

## 基本情報

- 状態: in_progress
- 現在工程: 実施(P4 着手前)
- 最終更新: 2026-11-24
- 最新作業記録: 0008-p3-read-eps-jobs-cluster-meta.md

## 現在の状況

プラン(0002)承認済み。P0〜P3 完了、レビュー R-A 完了。ブランチ `feature/implement-admin-api`(開始 SHA `cedcd5667638ec18eaf6ee501963ab356d33ed5f`)。P3 は検証再実行済み(pytest 1735 passed、ruff・format・lock OK)、コミット済み。
EP-09・10・12・14 と導出(derivation)・lock_view・stalled_check を実装済み。

## 次のアクション

1. P4(EP-01・02・11)を code-implementer に依頼
2. P4 完了後、レビュー R-B(比較基準は R-A 完了コミット `aa88b9b`。code-reviewer + test-reviewer 並列)
3. 指摘対応後、P5(書き込み系・Crawler 中継)へ

## 未解決事項

- 9200 を別プロジェクトの Fess が使っている場合のスモーク(P7)は、止めずにユーザー判断を仰ぐ
- `ClientDisconnect` のログ水準は P5 以降で判断
- `tzdata` の直接依存化(P7)、README の Docker 起動例更新(P7)
- AAM-U-7、BAPI-U-2 の残りは実装時に確認
- クエリの意味の実機確認(AAA-U-1〜3)・`cat.*` の実際の列・`relocating` の `node` 表記は P7 スモーク
- 設計書追従改訂の申し送り: 0004(4 件)・0005(5 件)・0006(ErrorCode の固定文 10 件)・0008(6 件。B 2.2 の `unavailable`、`failure_detail`、`cat.shards`、改行入り `job_id` など)
- 据え置き: `search_index_reader` の `parse_uncounted_search` 切り替え(P4 で再検討)、`test_secret_output.py` の DNS 依存

## ユーザー判断待ち

- なし

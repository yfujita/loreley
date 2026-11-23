# タスク状態

## 基本情報

- 状態: in_progress
- 現在工程: レビュー R-B 再レビュー(指摘対応後)
- 最終更新: 2026-11-24
- 最新作業記録: 0010-review-b-and-fixes.md

## 現在の状況

プラン(0002)承認済み。P0〜P4 完了、レビュー R-A 完了。R-B は code-reviewer が指摘なし、test-reviewer が Important 2 件(I1・I2)を指摘し、修正・検証再実行済み(pytest 1956 passed、ruff・format・lock OK)、コミット済み。
ブランチ `feature/implement-admin-api`(開始 SHA `cedcd5667638ec18eaf6ee501963ab356d33ed5f`)。
test-reviewer に I1・I2 の解消を再レビュー中(src の変更は Nitpick の 14 行のみのため code-reviewer の再レビューは不要)。

## 次のアクション

1. 再レビューの結果を受け、Critical/Important が残れば修正
2. 解消後、P5(書き込み系 EP-03〜08・Crawler 中継)へ。最初に Crawler の実 API(`apps/crawler/src/loreley_crawler/api/`)と B 9.2 を突き合わせ、`SourceSettings` の共用の扱い(厳格 / nullable 分離)を判断する

## 未解決事項

- 9200 を別プロジェクトの Fess が使っている場合のスモーク(P7)は、止めずにユーザー判断を仰ぐ
- `ClientDisconnect` のログ水準は P5 以降で判断
- `tzdata` の直接依存化(P7)、README の Docker 起動例更新(P7)
- AAM-U-7、BAPI-U-2 の残りは実装時に確認
- クエリの意味の実機確認(AAA-U-1〜3、AAPI-U-7)・`cat.*` の実際の列・`relocating` の `node` 表記は P7 スモーク
- 設計書追従改訂の申し送り: 0004(4 件)・0005(5 件)・0006(ErrorCode の固定文 10 件)・0008(6 件)・0009(4 件)・0010(B 2.2 の列挙から EP-12・14 を外す、EP-09 のクエリ違反の返し方)
- 据え置き: `test_secret_output.py` の DNS 依存、`job_queries.get_job` の失敗集約の整理、`brief_fields` の型付け

## ユーザー判断待ち

- なし

# タスク状態

## 基本情報

- 状態: in_progress
- 現在工程: 実施(P7 着手)
- 最終更新: 2026-11-24

- 最新作業記録: 0016-review-c-front-rereview.md

## 現在の状況

プラン(0002)承認済み。P0〜P4 完了、レビュー R-A・R-B 完了(いずれも再レビューで指摘なし)。P5(P5a・P5b)と P6(EP-13・プローブ)が完了。EP-01〜14 の実装がそろった。ブランチ `feature/implement-admin-api`(開始 SHA `cedcd5667638ec18eaf6ee501963ab356d33ed5f`)。R-C 前半は code-reviewer が指摘なし、test-reviewer が Important 1 件(I1: EP-05〜08 の許可外メソッドの 405)を指摘し、修正・検証再実行済み(pytest 3246 passed、ruff・format・lock OK)、コミット済み。
Crawler 実 API と B 9.2 の突き合わせは重大な差なし(0012)。AAPI-U-12・AAA-U-4 は実機で確認済み。`SourceSettings` は厳格版(EP-03・04)と nullable 版 `StoredSourceSettings`(EP-01・02)に分けた(0013)。
残りは P7(OpenAPI・README・手動スモーク)。
R-C 前半の再レビューで I1 の解消を確認(新しい test-reviewer。元の agent は報告が受理されず打ち切り。0016)。Critical・Important なし。

## 次のアクション

1. P7 を実施: (a) OpenAPI・`openapi_export.py`・`server/` のテスト(code-implementer)、(b) README(document-writer。並行)、(c) tzdata の判断、Docker の確認、(d) 手動スモーク(メインエージェント)
2. 解消後、P7(OpenAPI の `requestBody` 宣言・422 除去・operationId・tags・README・手動スモーク)→ R-C(後半)→ task-reviewer → PR

## 未解決事項

- 9200 を別プロジェクトの Fess が使っている場合のスモーク(P7)は、止めずにユーザー判断を仰ぐ
- `ClientDisconnect` のログ水準は P5 以降で判断
- `tzdata` の直接依存化(P7)、README の Docker 起動例更新(P7)
- AAM-U-7、BAPI-U-2 の残りは実装時に確認
- P7 スモークの実機確認: AAPI-U-11(接続拒否時の `ConnectionError.info` の型)、AAA-U-10(期限後に残るスレッド)、Indexer の起動前 503 が外から接続拒否に見えるか
- クエリの意味の実機確認(AAA-U-1〜3、AAPI-U-7)・`cat.*` の実際の列・`relocating` の `node` 表記は P7 スモーク
- **P7 の要対応**: OpenAPI の `requestBody` が出ない(本文を `read_body_as` で読むため)、`PUT /sources/{id}` などに `422` が出る。`openapi_extra` で `requestBody` を宣言し 422 を除去する(0013)
- 設計書追従改訂の申し送り(0015、3 件。D 5.0 の `lock_state` を読む時刻、C 8.5 に Crawler 失敗の WARNING、C 11章の DNS)
- 設計書追従改訂の申し送り(0014、7 件。B 2.2 の列挙から EP-13 も外す、`HttpHealthProbe.check(url)`、`Connection: close`、`web` の空ファイル、R9 の AST 検査など)
- 設計書追従改訂の申し送り(0013、7 件。B 2.11 の `SourceSettings`、`ttl_*` の `field` 名、違反の 2 段返却、`connector_config` の NaN・無限大、`%0A` の `job_id`、`lock_state` を読む時刻、巨大整数の `type`)
- 設計書追従改訂の申し送り(0012): B 11 の AAPI-U-12・AAA-U-4 を「確認済み」に。`redirect=False` は urllib3 では冗長(害なし)
- 設計書追従改訂の申し送り: 0004(4 件)・0005(5 件)・0006(ErrorCode の固定文 10 件)・0008(6 件)・0009(4 件)・0010(B 2.2 の列挙から EP-12・14 を外す、EP-09 のクエリ違反の返し方)
- 据え置き: `test_secret_output.py` の DNS 依存、`job_queries.get_job` の失敗集約の整理、`brief_fields` の型付け、Protocol 整合テストの非公開 API 依存(Python 更新時)

## ユーザー判断待ち

- なし

# タスク状態

## 基本情報

- 状態: in_progress
- 現在工程: レビュー R-C 後半(P7)
- 最終更新: 2026-11-24

- 最新作業記録: 0018-p7-manual-smoke.md

## 現在の状況

プラン(0002)承認済み。P0〜P4 完了、レビュー R-A・R-B 完了(いずれも再レビューで指摘なし)。P5(P5a・P5b)と P6(EP-13・プローブ)が完了。EP-01〜14 の実装がそろった。ブランチ `feature/implement-admin-api`(開始 SHA `cedcd5667638ec18eaf6ee501963ab356d33ed5f`)。R-C 前半は code-reviewer が指摘なし、test-reviewer が Important 1 件(I1: EP-05〜08 の許可外メソッドの 405)を指摘し、修正・検証再実行済み(pytest 3246 passed、ruff・format・lock OK)、コミット済み。
Crawler 実 API と B 9.2 の突き合わせは重大な差なし(0012)。AAPI-U-12・AAA-U-4 は実機で確認済み。`SourceSettings` は厳格版(EP-03・04)と nullable 版 `StoredSourceSettings`(EP-01・02)に分けた(0013)。
P7 のうち P7a(OpenAPI の宣言・公開配線・`openapi_export.py`・server の結合テスト・`tzdata`・`ClientDisconnect`)と README が完了(pytest 3389 passed、コミット済み。0017)。P7 の手動スモークも完了(実 OpenSearch・Crawler・Indexer。EP-01〜14・障害系・OpenAPI の公開・ログ・Docker を確認し、専用スタックは後始末済み。0018)。
R-C 前半の再レビューで I1 の解消を確認(新しい test-reviewer。元の agent は報告が受理されず打ち切り。0016)。Critical・Important なし。

## 次のアクション

1. レビュー R-C 後半(code-reviewer + test-reviewer 並列。比較基準 `463a050`〜、対象 P7a・README・OpenAPI)
2. 指摘対応後、task-reviewer(タスク全体)→ 完了チェックリスト → PR 作成(ユーザー確認のうえ)

## 未解決事項

- 手動スモークで未確認(0018): AAA-U-10、実行中ジョブの取消・実ロックの解放・`lock_in_use`・`stalled=true`、`force_delete=true`、`relocating`・複数ノードの `cat.*`、AAPI-U-7(`existence`)、窓 10,000 の実データ、OpenSearch の部分失敗。結合テストのタスクへ申し送り
- `ClientDisconnect` は WARNING 1 行 + 400 に変更済み(0017)
- `tzdata` は直接依存化済み(上限 `<2027` は 2027 年に見直し)
- AAM-U-7、BAPI-U-2 の残りは実装時に確認
- AAPI-U-11・AAPI-U-12・AAA-U-4 は実機で確認済み(0018)
- 設計書追従改訂の申し送り(0017、7 件。D 4.12(c) の実装形と `servers` 固定、`ClientDisconnect` の確定、B 8.1 の EP-13 の 400、`ttl_*` の OpenAPI 型、`ErrorResponse.error.code` は `str` など)
- 設計書追従改訂の申し送り(0015、3 件。D 5.0 の `lock_state` を読む時刻、C 8.5 に Crawler 失敗の WARNING、C 11章の DNS)
- 設計書追従改訂の申し送り(0014、7 件。B 2.2 の列挙から EP-13 も外す、`HttpHealthProbe.check(url)`、`Connection: close`、`web` の空ファイル、R9 の AST 検査など)
- 設計書追従改訂の申し送り(0013、7 件。B 2.11 の `SourceSettings`、`ttl_*` の `field` 名、違反の 2 段返却、`connector_config` の NaN・無限大、`%0A` の `job_id`、`lock_state` を読む時刻、巨大整数の `type`)
- 設計書追従改訂の申し送り(0012): B 11 の AAPI-U-12・AAA-U-4 を「確認済み」に。`redirect=False` は urllib3 では冗長(害なし)
- 設計書追従改訂の申し送り: 0004(4 件)・0005(5 件)・0006(ErrorCode の固定文 10 件)・0008(6 件)・0009(4 件)・0010(B 2.2 の列挙から EP-12・14 を外す、EP-09 のクエリ違反の返し方)
- 据え置き: `test_secret_output.py` の DNS 依存、`job_queries.get_job` の失敗集約の整理、`brief_fields` の型付け、Protocol 整合テストの非公開 API 依存(Python 更新時)

## ユーザー判断待ち

- なし

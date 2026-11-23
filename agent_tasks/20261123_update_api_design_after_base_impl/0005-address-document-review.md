# 0005 document-reviewer(1 回目)の指摘への対応

作成: 2026-11-23(メインエージェント)

## レビュー結果(document-reviewer。比較基準 `c0b6e40`)

Critical なし。Important 2 件、Suggestion 6 件、Nitpick 1 件。HO-51 内訳の反映漏れ・旧構成の残り・実装との不一致は見つからなかった。B・C に要件外の変更なし。

## 対応

| 指摘 | 対応 |
| --- | --- |
| [Important] A が「サブアプリの `root_path` は確定」と書き、D は未検証としていて矛盾。未検証項目の ID がない | A の 5.4(194 行)・10.1(確認していないこと)・10.4・HO-48・改訂履歴を、「確定は外側アプリの `root_path`(プロキシ配下)・例外ハンドラ・アクセスログの適用範囲(AAM-K-5)。サブアプリへの `FastAPI(root_path=…)`・入れ子のマウント・OpenAPI の `servers`・`paths` は未検証で BAPI-U-2 に残す」に直した。BAPI-U-2 の行の対象と確認時期(admin 実装時)も更新。D の AAM-U-2 の行は、残る未検証を BAPI-U-2(A 10.4)に引き継ぐと書き換えた。**P-d の範囲を、プラン作成時より少し広げた(BAPI-U-2 に未検証 2 点を足した)** |
| [Important] A 9.1 の状態の凡例に「対応済み」がない | 9.1 の「状態の付け方」に「HO-51 だけは追従改訂を終えたので『対応済み』(2026-11-23)」を追記 |
| [Suggestion] HO-51 内訳が未来形のままで経緯の記録と分からない | 内訳の見出し直後に「申し送り当時の記述(2026-11-23 に対応済み。反映先は D の改訂履歴と 4.12)。旧名称は経緯の記録として残す」の注記を追加 |
| [Suggestion] 推測・未検証が事実の書き方 | D 4.2 の `root_path`「壊れうる」に「推測。実験もテストもしていない。未検証。BAPI-U-2」を付けた。D 4.12(c) の `ClientDisconnect` は「推測している(未確認。基盤にコードもテストもない)」に直し、D 8.1「確認していないこと」に `ClientDisconnect` を追加 |
| [Suggestion] AAM-K-5 の出典がアーカイブで切れる | 出典欄に「タスク完了後は `agent_tasks/_archive/` 配下。承認は同タスクの 0002 に記録」を追記(0001 のヘッダーは作成時点の「承認待ち」のまま残る。作業記録は書き換えない方針) |
| [Suggestion] AAM-P-23 の区分欄が区分の語で始まらない | 「確定(AAM-K-5 に移した。ゲート3の承認済みの案からユーザー回答で変更。2026-11-23)」から始めた |
| [Suggestion] 内容を変えた AAM-P-2・P-3・P-14・P-17 の区分が変更前のまま | 区分欄を「承認済みの案を実装に合わせて変更(HO-51。2026-11-23)。元の区分: …」にした。変更は HO-51 の内訳に挙がっていた範囲 |
| [Nitpick] 5.9 の `debug_access_log_paths=[HEALTH_PATH]` | `{HEALTH_PATH}` に修正 |
| [Nitpick] 「`method_not_allowed`で」の助詞 | 半角スペースを入れた |
| [Nitpick] 4.12(a) の tests に `conftest.py`・`log_records.py` がない | 追加 |
| [Nitpick] A 改訂履歴に 10.1 がない / A 10.4 の「実装時(admin 実装時)」の重複 | 改訂履歴に 10.1 を追加。確認時期を「admin 実装時」だけにした |
| [Nitpick] 5.9 で `create_health_router()` を infra 生成より前に置く | 対応しない(5.9 は概念の図で、4.1 の手順 5 とずれても誤りではなく、図の読みやすさを優先) |

## ユーザー確認が望ましい点(reviewer が挙げたもの。最終報告に含める)

1. 0000 の冒頭が「下書き」のままで、ユーザー回答は 0001 の 0 節にだけある。0000 はユーザー記載のため agent は書き換えない。
2. E・F の「HO-1〜HO-50」は 0000 の対象範囲外なので変更していない。A・B・C・D だけ揃った状態でよいか。
3. D 冒頭の関連 HO を HO-39・HO-48・HO-49・HO-51 に広げた(D 内の HO 参照と A 9.2 の出典から確定)。

## 変更したファイル

- `docs/v0.x/system-design/api/api-base-design-v0.1.md`
- `docs/v0.x/system-design/api/admin/admin-api-module-structure-v0.1.md`

## 未対応事項・次にやること

- 修正を document-reviewer で再確認する(Important 2 件の解消)
- task-reviewer

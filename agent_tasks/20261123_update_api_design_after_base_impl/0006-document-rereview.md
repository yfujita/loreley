# 0006 document-reviewer(再レビュー)と軽微な修正

作成: 2026-11-23(メインエージェント)

## 再レビュー結果

**残る Critical・Important: なし**。1 回目の Important 2 件(A・D の `root_path` の食い違い、A 9.1 の凡例)は解消。0005 の対応に、新しい矛盾・誤記は見つからなかった。5.9 の `create_health_router()` の位置を直さない判断は妥当。完了条件(0000)は、document-reviewer の観点では充足。

## 新たな指摘(Suggestion 1・Nitpick 2)と対応

| 指摘 | 対応 |
| --- | --- |
| [Suggestion] D 8.1「確認していないこと」に OpenAPI の `servers`・`paths` がない | 追記した |
| [Nitpick] AAM-K-5 の出典欄「承認は同タスクの 0002 に記録」が紛らわしい(0002 にあるのは、プランの承認) | 「プランの承認は同タスクの 0002 に記録」に直した |
| [Nitpick] A の HO-51 内訳の AAM-U-2 の項の `FastAPI(root_path=...)` が断定的 | 「(2026-11-23 の対応で、推測・未検証と整理した。BAPI-U-2)」を追記した |

いずれも注記の追加のみで、設計の内容は変えていない。修正後の再レビューは行わない(Critical・Important ではなく、文言の補足だけのため)。`git diff --stat c0b6e40 -- apps/` は空。

## 変更したファイル

- `docs/v0.x/system-design/api/admin/admin-api-module-structure-v0.1.md`
- `docs/v0.x/system-design/api/api-base-design-v0.1.md`

## 未対応事項・次にやること

- task-reviewer
- ユーザーへの確認事項(最終報告に含める): 0000 が「下書き」のままで回答は 0001 の 0 節にあること、E・F の「HO-1〜HO-50」を揃えるか、D 冒頭の関連 HO を 4 件に広げたこと、`apps/api/README.md` 冒頭の古くなった注記の扱い

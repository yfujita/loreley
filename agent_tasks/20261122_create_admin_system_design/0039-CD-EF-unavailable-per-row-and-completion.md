# 0039 C・D・E・F の追従(一覧の `unavailable` を行単位に)と再完了

日付: 2026-11-23
担当: document-writer(C・D 担当、E・F 担当。メインが記録)

## 変更ファイル(PR #10 レビュー指摘への対応の全体。0037・0038 を含む)

A・B(0038)、C(`admin-api-architecture-v0.1.md`)・D(`admin-api-module-structure-v0.1.md`)、E(`ui-admin-frontend-architecture-v0.1.md`)・F(`ui-admin-frontend-module-structure-v0.1.md`)。SD・PD・既存設計・機能設計・DS・画面仕様・apps/・CLAUDE.md は無変更。

## C・D の変更

- C: 3.2(d)(`msearch` の `responses[i].error` と `mget` の文書単位の失敗は、その結果が担う行または最上位の項目に帰属)、3.3 の R-3・R-4・R-9・R-11(失敗の単位)、5.2 手順 1(`stalled` の失敗は失敗した文書のソースの行だけ。`mget` 全体の失敗は `running` を持つ全行)、5.5・5.6(R-3 の失敗は全行の `last_crawl`・`last_completed_at`、`delete_job` は `status=deleting` の行だけ、`existence` の失敗は全行)、5.8(`unavailable` の位置とキーの説明、位置併記のキー対応表、「失敗の帰属」表)、5.10・8.6・11 観点 6(source-a の未実行でキーなしと source-b の失敗でキーありの区別)、12 章。5.4 の `JobBrief` 導出表は変更不要(`JobBrief` 自体は `unavailable` を持たない)
- D: 3 章(`SourceListItem`・`JobListItem`・各タブの行 DTO、`Unavailable` 型、`unavailable.py`)、4.4・4.5・4.7(`unavailable.py` を単一応答の最上位用と一覧の行用の 2 関数に区別、`services` が読み取り結果を行の ID で持って帰属)、4.8(Reader の `mget` 結果を ID をキーにした対応で返す)、5.3・5.7・5.8(シナリオ)、7.3 観点 6、8.3・8.7
- 新規 **AAA-P-45**(C)・**AAM-P-29**(D): 承認済みの案(ゲート3。2026-11-23)の修正(PR #10 のレビュー指摘への対応。B の AAPI-P-42 に依存)。AAA-P-21・22・25・35、AAM-P-7 の区分欄に修正を明記。`-K-`・新規 U・I-n なし

## E・F の変更(0038 の報告)

- E: 5.7(S1・J1・X1 の `unavailable`)、5.9(判定は「その行(または最上位)の `unavailable` のキー」。旧規則「一覧でキーがあり行が `null` なら取得できません」は廃止)、6.2、12.1・12.6・改訂履歴。新規 FARC-P-39
- F: 3.5(`rowUnavailableReason`・`topUnavailableReason`、`cellState` は引く対象の `unavailable` を引数に取り、薄いラッパー `rowCell`・`topCell`。旧 `isRowUnavailable` 廃止)、3.9、5.5(X1 の `tab_counts` は `topCell`、各行の `existence` は `rowCell`)、7 章(source-a の未実行・source-b の失敗の区別、全行失敗、1 行だけの失敗が他の行に影響しないこと)、8 章。新規 FMOD-P-33。FARC-P-27・P-36、FMOD-P-14・P-31 の区分欄に修正を明記
- 区分の更新: 新規・変更はいずれも「承認済みの案(ゲート3)の修正(PR #10 のレビュー指摘への対応。2026-11-23)」。`-K-`・新規 I-n なし

## 留意点

- C の整理: B の記述では EP-01 の件数も「ソースごとのサブ要求」と読めるが、C の R-3 と EP-01 の件数は 1 回の検索なので失敗は全行とした。行ごとに成否が分かれるのは、ロック文書の `mget`(文書単位)と確認読み(`stalled` など)、EP-11 の `existence`(文書単位)。矛盾はない。メインの grep では B に「ソースごとのサブ要求」の表現は残っていない
- `latest_for_source`・`rerunnable` は EP-10(単一応答)の項目で、B 2.2 でも最上位のまま
- 実機未確認: `msearch` の `responses[i].error`、`mget` の文書単位エラーの形は AAA-U-2

## 自己検算(writer・メイン)

- 表の列数(バッククォート内の `|` も区切りとして数える): A 23 表・B 61 表・C 33 表・D 17 表・E・F で崩れ 0。コードフェンスは閉じている
- ID 参照の未定義 0・未参照 0(AAA 63・AAM 42 定義。AAPI-P-42・FARC-P-39・FMOD-P-33 を含む)、欠番 ID への参照なし
- `items[].…` 形式の `unavailable` キー: 残存は「使わない」という禁止の記述のみ(メインの grep でも、JSON のキーや `unavailable.items[]` 形式は 0 件)
- B の EP・code・項目名は不変

## 区分変更の明示(完了報告)

ゲート3(2026-11-23)でユーザーが承認した AAPI-P-16・25・27・30(および派生の AAA-P-21・22・25・35、AAM-P-7、FARC-P-27・36、FMOD-P-14・31)の内容を、PR #10 のレビュー指摘(ユーザー指示「指摘が適切であれば対応して」)に基づいて変更した。変更内容は AAPI-P-42・AAA-P-45・AAM-P-29・FARC-P-39・FMOD-P-33 に記録。確定にはしていない。

## 未対応事項

0036 の未対応事項(HO-50 ほか)に変更なし。再レビュー(document-reviewer)は実施していない: 変更が `unavailable` の位置とキーの規則に限られ、設計の他の部分は不変であること、writer が各文書で機械チェックを実施し、メインが旧表記・文言の食い違いを grep で確認したことによる。必要なら PR レビューで確認してもらう。

## 次

`feature/admin-system-design` にコミットして push(PR #10 に反映)。STATUS.md は done

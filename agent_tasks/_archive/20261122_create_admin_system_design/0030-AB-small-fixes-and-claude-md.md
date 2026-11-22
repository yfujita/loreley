# 0030 A・B の小修正(C・D の修正反映)と CLAUDE.md の参照先更新

日付: 2026-11-23

## A・B の小修正(B 担当 writer。メインが記録)

変更ファイル: A(`api-base-design-v0.1.md`)・B(`admin-api-v0.1.md`)のみ。区分はすべて案(ゲート3)。EP 番号・パス・承認済みの code 名・項目名は不変。新規 ID なし(既存 ID の記述更新のみ)。

- A 5.6・BAPI-P-12: OpenSearch の再試行を「接続エラー(接続タイムアウトを含む)と、429・500・502・503・504 の 5 値。読み取りタイムアウトは再試行しない」に。「5xx すべて」より狭い(501・505 は再試行しない。C 3.7 の `retry_on_status`、AAA-P-8)
- A 5.5・BAPI-P-17: uvicorn は `log_config=None`・`access_log=False` で起動しアクセスログは自前。想定外の例外は middleware が 500 `internal_error` に変換し再送出しない(D 4.1、C 8.5、AAA-P-38)
- B 9.1・2.3・2.6: `SSLError` は接続の確立中の失敗として送る前に分類し 503 `crawler_unreachable`(MVP は `CRAWLER_URL` が http 限定=BAPI-P-24 のため通常は起きない。https を許す将来は分類を見直す=AAA-P-41)。AAPI-U-12 とは別の扱い
- B 2.2・AAPI-P-25: C の AAA-P-39 との食い違いはなかったが、OpenSearch が HTTP 200 のまま返す部分的な失敗(`mget` の文書単位 `error`・`found` が真偽値でない、検索の `_shards.failed>0`・形の異常)は成功と読まずその読み取りの失敗として扱い、`timed_out=true` は `timeout` と一文追加。実機の応答の形は AAA-U-2
- 自己検算: ID 参照の未定義 0・未参照 0、A 12 表・B 60 表の列数崩れ 0、JSON 例パース可、不採用項目の残存は記録のみ
- C・D への影響なし(同内容を C 3.7・4.3・8.5・AAA-P-39 に反映済み)

## CLAUDE.md の参照先更新(メイン)

`CLAUDE.md` の「参照先」の `ui-admin/` の行の下に 2 行を追記した(他の行は無変更)。

- Admin View のフロントエンド設計: `docs/v0.x/system-design/ui-admin/frontend/`(同上。アーキテクチャ・モジュール構成)
- api の共通設計と Admin API の設計: `docs/v0.x/system-design/api/`(同上。`api/admin/` が Admin API の仕様書・アーキテクチャ・モジュール構成。他文書への追従改訂の申し送りは `api/api-base-design-v0.x.md` の申し送り章に集約)

## 次

フェーズ5の統合(document-writer。申し送りの A 9章への一元化、`HO-n` の実番号化、「作成予定」の語の置換、6 文書の参照・用語の整合)の報告待ち → R4 → ゲート3

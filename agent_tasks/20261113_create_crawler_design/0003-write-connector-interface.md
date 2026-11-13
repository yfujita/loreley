# 0003 connector-interface 作成(P0+P1)とR1レビュー

- 日付: 2026-11-13
- 実施: P0(メイン)、P1(document-writer)、R1(document-reviewer。初回+再レビュー)
- 結果: R1 通過(Critical/Important 解消。軽微指摘も反映済み)

## 実施内容

- P0: `docs/v0.x/system-design/crawler/connector/` を作成。基準SHA `5eeb7a4`。
- P1: `docs/v0.x/system-design/crawler/connector/connector-interface-v0.1.md` を新規作成(0002 の章立て案どおり1〜11章)。
- R1 初回レビュー: Critical 0 / Important 6 / Suggestion 8 / Nitpick 3。Important を含めすべて反映。
- R1 再レビュー: Important 6件すべて解消、新たな Critical/Important なし。Suggestion A〜C・Nitpick 3件が出たため反映。「P2に進んでよい」の判定。

## 変更ファイル

- `docs/v0.x/system-design/crawler/connector/connector-interface-v0.1.md`(新規)

## 事実確認の結果

- batch の `documents[]` に `document_id` はない。Indexer が算出して応答で返し、Crawler の値とは照合しない。`last-seen` の `document_ids` と終了通知の ID 一覧は Crawler 算出のため、算出がずれても Indexer では検出されない(二重実装対策: CI-P-4、最終採否は CI-U-1)。
- `\`→`/` の衝突は実在: indexer-api 3.3 は「`/` に統一」とだけ書き、Indexer 実装(`document_id.py`、README 6章)は `\` も置換する。`a\b.txt` と `a/b.txt` が同一 `document_id` になることを実計算で確認(I-10)。Linux で `\` がファイル名として使えることは推測(実機未確認)。
- サンプルベクタは `API_EXAMPLE_VECTORS` と一致(レビュアーも独立に再計算して確認)。導出ベクタ5件も Indexer 実装と一致。Indexer のテストには未収録。
- oversize: PD v0.19 4.2 と Indexer K65(2026-11-11 承認)は Crawler 送信前拒否を含む二重防御を確定としている。PD 9.2 #8 が未決とするのは表示・記録先・ジョブstatusへの影響のみ。「送信前拒否の有無を未決」とするのは indexer-api 4.9 だけ(I-11)。

## 主な設計判断(いずれも「案」。確定はIndexer API由来・K65・Q2回答のみ)

- 正規化・検証は共通処理(Crawler本体)が一律に行う。Connector は規則適用前の `external_id` を返す。`DocumentRef` に不透明な `locator` を持たせる。
- 規則は6本。適用順序は ①孤立サロゲートのID用エスケープ → ②NFC → ③`\`→`/` → ④検証(先頭 `/`・空・NUL・4096バイト)。
- 孤立サロゲートのID用エスケープ(案A・CI-P-10): 孤立サロゲート1文字を U+FFFD + `u` + 4桁大文字16進に置換。入力中の U+FFFD は2文字化。決定的・単射・`\` を含まない。レビュアーが小さな文字集合の総当たりで衝突なしを確認。
- `fetch(ref, max_bytes)`: 上限値は Crawler 設定(Indexer の `max_raw_bytes` と整合)を共通処理が渡し、読み取り中の超過で中断して `oversize`(CI-P-14)。
- `content_hash` と `size` は共通処理が実際に送るバイト列から導出(CI-P-3)。
- エラー: `ConnectorError {category, scope, retry, message}`。属性は `scope`(source/document)と `retry`(transient/permanent/unknown)の単一値。`source_unreachable`(transient)・`source_not_found`(permanent)・`source_access_denied`(permanent)、`connector_internal_error` は発生点で分ける(列挙・create は source、取得は document)。
- 識別子由来の document scope の失敗(`invalid_external_id`・`external_id_collision`)は共通処理が付与する。`invalid_external_id` の文書は `last_seen_at` 要請・取得に進めない。`external_id_collision` の扱いは CI-U-2(未決)。
- 列挙は `Completed` か `Failed` で必ず終わる(CI-P-7)。事前確認(preflight)は置かない(CI-U-6)。
- CI-K-10(Crawler側 oversize 拒否の実施=確定)をライターが新設。根拠は PD 4.2 と K65 の確定記述で、レビュアーが妥当と判定。

## 採番ID

- CI-K: 1〜10(確定)/ CI-P: 1〜16(案)/ CI-U: 1〜10(未決)
- CI-U: 1 二重実装対策の最終採否 / 2 `external_id` 衝突の扱い / 3 oversize の方式・上限値・記録先・ジョブstatusへの影響・ID一覧への載せ方 / 4 `invalid_external_id` 文書の記録方法 / 5 `source_updated_at` 取得不能時の値 / 6 事前確認の要否 / 7 認証情報の参照名の解決 / 8 `title`・`path` の欠落・長さ / 9 Connector呼び出しとリース更新の並行モデル / 10 共通処理のID集合の保持量と保持できない場合
- 既存設計との不整合: I-10(`\`・NFC/NFD による `document_id` 衝突)、I-11(oversize送信前拒否の食い違い)。I-12〜I-19 は未使用。

## 次の文書への申し送り(interface 11.6)

- architecture へ: CI-U-2、3、4、6、10。リトライ・スキップ規則を interface 6章の属性(scope/retry)と整合させる。`connector_internal_error`(取得時 document)の連続発生時の打ち切りは architecture に委ねられている。
- FS 文書へ: 孤立サロゲートは共通処理が一律に処理するため「発生状況の説明のみ」でよい。MIME対応表、`title` の取得不能時の値、`size_hint` の有無、衝突への対応、マウント外れを `source_unreachable`/`source_not_found` のどちらにするかの判定。
- Web 文書へ: 9章の論点 A〜D(列挙の完全性の定義、列挙と取得の一体化、`Last-Modified` 欠落、429 の待機)と CI-U-5、CI-U-7。
- module-structure へ: CI-U-1、CI-U-9、`ConnectorType` と共通処理の配置。
- 11.5 の `agent_tasks/.../0001-clarify-requirements.md` への参照(I-1〜I-6 の所在)は、architecture の横断一覧ができた後に差し替える。

## 未対応事項

- ユーザー判断が将来必要になり得る点(設計書内では案・未決・I-n として記録済みで、現時点では作業を止めない):
  - I-10: Indexer の `\`→`/` 規則自体の是非(Indexer設計側の課題。Crawlerは実装に合わせる)
  - I-11: indexer-api 4.9 の記述更新(Indexer設計書は書き換えない方針)
  - 孤立サロゲートのID用エスケープ方式の最終決定(案)
- 他文書への修正要望: なし。
- 次: P2 crawler-architecture(R2 ゲートつき)。

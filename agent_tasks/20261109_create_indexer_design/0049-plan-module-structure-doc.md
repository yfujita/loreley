# 0049 プラン更新: Indexer モジュール構成設計書の追加

## 経緯
ユーザーから「Indexer のモジュール構成設計書を作成して。構成がすぐわかるよう、読みやすさを最優先に」と指示された(2026-11-10)。具体的な指示なので承認として扱う(承認の扱いのメモリに従う)。

## スコープの変更
- 追加する成果物: `docs/v0.x/system-design/indexer/indexer-module-structure-v0.1.md`(新規。文書単位の版は v0.1 から)。
- 既存の v0.9 設計書(architecture / api / schema)と PD は変更しない。0000 も変更しない。
- 元にする資料: `indexer-architecture-v0.9.md`(責務・処理)、`indexer-api-v0.9.md`(API)、`search-index-v0.9.md` / `loreley-deletions-v0.9.md`(Schema)、`agent_tasks/20261110_implement_indexer/0000-requirements-definition.md` のディレクトリ構成(`apps/indexer/src/` の extraction / indexing / deletion / summarization / storage)。

## 方針
- 読みやすさを最優先。1ページ目で全体像(構成図・モジュール一覧)が分かる。詳細は後ろに回す。
- モジュールごとに「何をするか」「しないこと」「依存先」「元の設計書の節」を同じ形式で書く。
- 図(Mermaid)と表を使う。長文の説明を避ける。
- architecture v0.9 の仕様・数値は変えない。モジュール分割の判断は「案」と明示し、確定扱いにしない。
- 作成は document-writer、レビューは document-reviewer(可読性・構成の分かりやすさ、v0.9 との整合)。

## 作業手順
1. document-writer が作成。
2. document-reviewer がレビュー。Critical / Important は修正。
3. メインが作業記録(0050)を作成。

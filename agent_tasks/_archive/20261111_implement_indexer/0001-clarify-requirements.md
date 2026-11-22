# 0001 要件確認(確定した要件)

日付: 2026-11-11 / 実施: requirements-clarifier(2回)+ユーザー回答

## ユーザー回答(推奨案を選択)

- Q1 実装範囲: 全モジュール実装(LLMの具体プロバイダは除く)
- Q2 設計書の「案」「未決」: 案は実装仕様として採用。未決の数値は設定可能な仮値(上限付き、K39)。未決の挙動は案に近い側に倒し、一覧を作業記録に残す。要確認事項はプランで個別提示
- Q3 テスト: OpenSearchアクセス層とLLMをインメモリfakeに差し替えて単体テスト(競合再現フック含む、arch 16.1整合)。U-31の実機確認は範囲外・持ち越しとして記録

## 確定した要件

### 目的・位置づけ
- Indexer(`apps/indexer`)を設計書に従って実装する。Crawlerからのhttpを受け、登録・削除判定・削除実行・要約生成を行う唯一のコンポーネント
- 現状は空の `apps/indexer/Dockerfile` のみ。Indexer以外(Crawler・api・web・OpenSearch実体・compose)は対象外

### 仕様の正本
- `docs/v0.x/system-design/indexer/`: indexer-architecture-v0.9(arch)、indexer-api-v0.9(api)、indexer-module-structure-v0.3(module)
- `docs/v0.x/system-design/opensearch/schema/`: loreley-deletions-v0.9、search-index-v0.9(要件定義の参照パスは `schema/` が抜けている。読み替える)
- プロダクト設計は v0.18 が最新(v0.17から仕様変更なし、用語統一のみ)。v0.18を参照する
- 要件定義(0000)は書き換えない

### 実装範囲
- `api`: 8 API(開始通知、終了通知、Status、バッチ登録、`last_seen_at`部分更新、ソース削除1〜3)。形式検証と共通エラー形式。業務判断はしない(R4)
- `crawl_runs/lifecycle`: 開始・終了通知、世代管理、受理条件の照会(`rewrite_mode`つき)、Status、起動時の未完了結果の `failed`(`indexer_restart`)化、同一ソース直列処理
- `crawl_runs/deletion`: 削除判定(メンテナンスフラグ、件数照合、割合ルール)、バッチ削除(TTL再確認と条件付き削除)、ソース削除1〜3(`delete_by_query`再実行は回数上限つき)
- `documents`: 登録(`document_id`算出、ロック所有確認、新規/更新/変更なし判定、`rewrite_mode`、409時の読み直し)、`last_seen_at`部分更新(max比較)、extraction(txt/Markdown/HTML/PDF、UTF-8・Shift_JIS/CP932、正規化、切り詰め`truncated`、`text_hash`)、summarization(非同期生成の枠組み、書き戻し条件判定、起動時再走査。既定は無効)
- `infrastructure/opensearch`: 検索インデックスとStore層の窓口(Repositoryインターフェース)。結果区分(成功・409・文書なし・文書固有の拒否・全体異常)。`loreley-jobs`は読み取りのみ
- `infrastructure/llm`: インターフェースのみ(具体プロバイダなし、既定は無効)
- `main.py`(組み立て、起動時整理をHTTP受付前に実行、再走査は並行)、`config.py`(値は`main.py`が渡し、各モジュールは`config.py`に依存しない)、`Dockerfile`

### テスト方針
- OpenSearchアクセス層とLLMをインメモリfakeに差し替える。fakeは409再現用フックを持つ
- U-31(実機OpenSearchでの確認)は未対応・持ち越し。fakeのみでは `_seq_no` による楽観ロック、`delete_by_query`の競合、`search_after`などの実挙動は検証できない点を明記する

## 完了条件(案。プランで承認対象)

1. `apps/indexer` が module v0.3 の構成(3層、`main.py`、`config.py`)で存在し、依存ルールR1〜R9に反しない(import方向をテストまたはlintで確認)
2. api 1章の8 APIがエンドポイント案どおり応答する。形式不正は400、エラーは共通形式(TestClientで検証)
3. 登録: 新規・更新・変更なし・`rewrite_mode`・受理条件拒否(1件も書かない)・ロック不所有・409時の再判定(上限あり)・抽出失敗が文書ごとの結果区分で返る
4. `last_seen_at`部分更新: `updated`/`unchanged`/`not_found`/失敗の区分、max比較で古い値に戻らない
5. 抽出: txt/Markdown/HTML/PDF、UTF-8・Shift_JIS/CP932、サイズ上限での切り詰めと`truncated`、`text_hash`が決定的
6. `crawl_runs`: 世代更新、旧結果の`superseded`化、終了通知の事前照合と再送判定、同一ソース直列処理、Status、起動時の`failed`(`indexer_restart`)化
7. 削除: メンテナンスフラグ・件数不一致・割合超過で削除せず理由つき終端。通常時はバッチごとにTTL再確認して条件付き削除。ソース削除1〜3が再実行可能
8. 要約: 既定は無効でLLMを呼ばない。有効時(fake)は`pending`かつ`content_hash`・`text_hash`一致時のみ書き戻し、不一致は破棄。409は読み直し、上限超過は`pending`のまま。起動時再走査が動く。LLM失敗は登録に影響しない
9. 起動順序: 削除結果の整理がHTTP受付より先に完了する
10. ログに本文・秘密情報を出さない(R9。テストでログ出力を検査)
11. `uv run pytest`、`uv run ruff check`、`uv run ruff format --check` がすべて成功。結果を作業記録に貼る
12. `docker build apps/indexer` が成功し、起動して`/healthz`相当に応答する。Dockerが使えない場合は未実施・持ち越しと記録する
13. 仮値一覧、「案」採用判断の一覧、U-31等の持ち越し一覧が作業記録に残っている

## 成果物(案)

- `apps/indexer/src/loreley_indexer/` の全モジュール
- `apps/indexer/tests/`(単体テスト、インメモリfake、競合フック、APIテスト、抽出サンプル)
- `apps/indexer/pyproject.toml`、`uv.lock`、ruff・pytest設定
- `apps/indexer/Dockerfile`(現状は空)、`apps/indexer/README.md`(起動・設定・テスト手順)
- 作業記録: 仮値一覧(設定名・既定値・上限・根拠ID)、「案」「未決」を倒した側の一覧、ロック文書・メンテナンスフラグの仮定義、インデックス名・エイリアス名の仮定、U-31持ち越し・未対応事項

## 前提として置く技術選定(プランで明示し承認対象)

Python 3.12、uv、FastAPI + uvicorn + pydantic v2、opensearch-py(同期/非同期はプランで決める)、pytest、ruff、HTML抽出はbeautifulsoup4+lxml、PDFはpypdf、文字コードは標準codecs(UTF-8→CP932)。追加依存は最小限。設定は環境変数(pydantic-settings)。`apps/indexer`内で完結させる。

## 前提・方針

- MVP前提(認証なし、単一ホスト、単一Indexer、直列実行)
- ロック文書・メンテナンスフラグの形式は設計書に未定義(Indexerは読み取り側)。Repositoryインターフェースと仮フィールド定義を作り、仮定義を作業記録に残す
- インデックス名・エイリアス名は未決のため、設定で変更可能な仮名を置く

## 未対応事項・プランで扱う事項

- 要件定義の空欄(制約・前提条件/完了条件/成果物)は上記案で補完。`0000`への反映はユーザー任意
- U-31の実機確認は持ち越し
- 未決挙動(U-5原本サイズ超過、U-26`content_hash`照合、API-U-13ロック失敗時の部分結果、API-U-7、U-14削除処理の開始契機、U-20再起動時整理、`fetched_at`/`metadata`を含む入力の扱い等)の一覧と、倒す側の案をプランで提示
- ソース削除2・3のロック所有確認(M-7、API-U-14)の案をプランで提示
- module v0.3 が存在しない過去タスク `20261110_implement_indexer` を参照している(軽微、実装に影響なし)
- 実装フェーズ分割の推奨: 基盤・infrastructure → documents → crawl_runs → api・main → Dockerfile・README。レビューは code-reviewer / test-reviewer、最後に task-reviewer

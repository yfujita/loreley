# タスク状態

## 基本情報

- 状態: done(実装・レビュー・タスクレビュー完了。PR #18 を作成済みで、外部レビューの指摘に対応済み)
- 現在工程: 完了(PR #18 のマージ待ち)
- 最終更新: 2026-11-24
- 最新作業記録: 0022-pr18-external-review-fixes.md

## 現在の状況

Admin API(EP-01〜14、ベース `/api/admin/v1`)を `apps/api` に実装し、完了した。ブランチ `feature/implement-admin-api`(開始 SHA `cedcd5667638ec18eaf6ee501963ab356d33ed5f`)。

- 検証: `uv run pytest` 3423 passed(PR 提出時 3410。外部レビュー対応でテストを 13 件追加。0022)、`ruff check`・`ruff format --check`・`uv lock --check` すべて通過(`task-reviewer` が再実行して確認)
- 実装: 読み取り系 EP-01・02・09・10・11・12・14、書き込み系(Crawler 中継)EP-03〜08、ダッシュボード EP-13、OpenAPI の書き出し(`openapi_export.py`)と `OPENAPI_ENABLED` の公開、`apps/api/README.md` の更新
- レビュー: R-A・R-B・R-C(前半・後半)とその再レビューで Critical・Important はすべて解消。`task-reviewer`(タスク全体)も Critical なし・差し戻し不要(0021)
- 手動スモーク(実 OpenSearch・Crawler・Indexer): EP-01〜14・障害系(Crawler 停止・OpenSearch 停止)・OpenAPI の公開・ログ・Docker を確認し、専用スタックは後始末済み(0018)
- PR #18 への外部レビュー(Critical 0 / Important 1 / Minor 1)に対応済み(0022): I-1(EP-11 の `tab` が OpenAPI 上は任意だった。`tab` を必須・列挙に、`items_per_page` と EP-09 の `status` の列挙も反映)、M-1(Crawler 応答の上限を 2 MiB に)。修正差分の `code-reviewer` は指摘なし
- 設計書(`docs/`)・`apps/crawler`・`apps/indexer`・compose・`Dockerfile`・infra は変更していない。差分は `apps/api` と `agent_tasks` のみ(開始 SHA からの 20 コミット・249 ファイル・約 33,000 行の追加。うち `apps/api` は 226 ファイル)

## 次のアクション

1. PR #18(https://github.com/yfujita/loreley/pull/18)のマージ。追加の指摘があれば対応し、作業記録を残す(ユーザーの承認を得て 1 本で作成。PR 説明に「既知のリスク」を記載済み)
2. 設計書の追従改訂を別タスクとして起票するか決める
3. 結合テストのタスクを起票するか決める

## 未解決事項

申し送りは 0021 に集約している(各記録の該当節が正本)。

- **設計書の追従改訂の申し送り(別タスク)**: 0021 の A。0004・0005・0006・0008・0009・0010・0012・0013・0014・0015・0017・0019 に分散。主なもの: D 5.0 の `lock_state` を読む時刻、B 2.2 の単一応答の列挙から EP-12・13・14 を外す、B 11 の AAPI-U-12・AAA-U-4 を「確認済み」に、B 2.11 の `SourceSettings`、`ErrorCode` の固定文 10 件、D 4.12(c) の実装形
- **設計書の追従改訂の追加(0022)**: C 4.1・C 9章の「Crawler の応答本文は 1 MiB まで」を 2 MiB に(非 ASCII だけの 1 MiB 級の設定では `\uXXXX` 表記で膨らみ、2 MiB でも足りない可能性がある)
- **OpenAPI の `ttl_days`・`ttl_seconds`(`integer | null`)の不整合は、フロントエンドの型生成を始める前に対応する**(0017・0021 の C。外部レビューも同じ推奨。0022)
- **結合テストのタスクへの申し送り**: 0021 の B。手動スモークで未確認(AAA-U-1〜3 の一部・AAA-U-7・AAA-U-10、実行中ジョブの取消・実ロックの解放・`lock_in_use`・`stalled=true`、`force_delete=true`、`relocating`・複数ノードの `cat.*`、AAPI-U-7、窓 10,000 の実データ、OpenSearch の部分失敗、`ClientDisconnect` の実機、BAPI-U-2 の残り(入れ子のマウントと `FastAPI(root_path=…)`))
- **据え置き(軽微)**: 0021 の C(`test_secret_output.py` の DNS 依存、`job_queries.get_job` の失敗集約、`brief_fields` の型付け、`openapi_enabled` の二重、`packaging` の明示、Protocol 整合テストの Python 3.12 前提など)
- **`apps/api/Dockerfile` 11 行目のコメント「現時点の `api` は基盤だけ」が古い**: HO-36 で Dockerfile に触るときに直す
- **`tzdata` の上限 `<2027`**: 2027 年に見直す
- **OpenAPI JSON のコミット先と Hey API 側の読み込み**: フロントエンドのタスク(FARC-P-6)

### 既知のリスク(設計どおり。対策は別タスクの判断)

認証なしの `api` が破壊的操作(削除ジョブ、ロック解放、クロール起動、取消)を公開する(HO-40)。本文なしの POST(EP-05・06・07)は `Origin` を問わず処理される(HO-41。0013 のテストで確認)。README 第 2 章に記載済み。信頼できるネットワークにだけ公開すること。

### 解消済み(参考)

- `ClientDisconnect` は WARNING 1 行 + 400 に変更し、テストを強化済み(0017・0019)
- `tzdata` は直接依存化済み(0017)
- AAPI-U-11・AAPI-U-12・AAA-U-4・AAM-U-7 の前半・BAPI-U-2 の `servers`・`paths` は確認済み(0012・0017・0018)
- `SourceSettings` の共用の判断(厳格版と nullable 版に分離。0013)、OpenAPI の `requestBody` の宣言・422 の除去(0017)

## ユーザー判断待ち

- **設計書の追従改訂を別タスクとして起票するか**(0021 の A)
- **結合テストのタスクを起票するか**(0021 の B)

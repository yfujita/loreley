# 0019 レビュー R-C 後半(P7a・README)と指摘対応

日付: 2026-11-24

## レビュー結果

比較基準 `463a050..b9f09e4`。`code-reviewer`・`test-reviewer` を並列実施(README の正確さは `document-reviewer` を省略した代わりに `code-reviewer` が確認)。

### code-reviewer: Important 1(Critical 0 / Suggestion 3 / Nitpick 3)
- **Important**: README 5 章冒頭の「空文字を渡した「任意」の URL・文字列は、未設定として扱う」が `config.py` と食い違う。空文字を未設定にするのは `OptionalText` 型の項目(`DASHBOARDS_HEALTH_URL`・`EMBEDDING_HEALTH_URL`・`LLM_HEALTH_URL`・`DASHBOARDS_URL`・`CRON_TIMEZONE`)だけで、`OPENSEARCH_USERNAME`・`OPENSEARCH_PASSWORD`・`OPENSEARCH_CA_CERTS_PATH` は `str | None` のまま空文字は未設定にならない(メインエージェントも `config.py` で確認。`LORELEY_API_OPENSEARCH_USERNAME=` だけを渡すと `opensearch_credentials_incomplete` で起動失敗)
- Suggestion: (1)`app.openapi` の差し替えの「初回」判定が FastAPI の内部キャッシュ(`openapi_schema is None`)に依存。調整が失敗した後の 2 回目以降が未調整のスキーマ(422 入り)を黙って返す/ルート変更による再生成で 422 が復活し得る (2)`tzdata` を直接依存にした理由・上限 `<2027` の見直しがコードに残っていない (3)`openapi_enabled` の持ち方が二重(`AdminSettings`・`create_admin_app` の引数)
- Nitpick: `ClientDisconnect` 分岐が `_too_large()` を使わず同じ `ApiError` を直書き/`_Unconnected.__getattr__` があらゆる属性で `RuntimeError`/Dockerfile のコメント「現時点の `api` は基盤だけ」が古い(今回の diff の範囲外)
- 指摘なし(良好): OpenAPI の宣言と B の一致(全 EP のステータス・タグ・`requestBody`・`operationId`・422 除去・`ErrorResponse`)、`OPENAPI_ENABLED` と書き出しの同一性、`servers` 固定の判断、`openapi_export`(環境変数なしで 2 回の出力が一致・接続しない)、`ClientDisconnect` の WARNING + 400 の判断、HO-40・41 の記述(実装・設計書・テストと矛盾なし)、EP 一覧・環境変数・Docker 例の事実確認、受け入れ基準 ④、スモーク(0018)との整合

### test-reviewer: Important 1(Critical 0 / Suggestion 3 / Nitpick 2)
- 50 件以上のミューテーションで、OpenAPI の構造・ステータス宣言・公開配線・server の結合テストはほぼすべて検出。受け入れ基準 ④ は実際のアサーションで検証済み。逆順実行・`tests/server/` の 5 回連続も安定
- **Important**: `ClientDisconnect` のテストが「ログに値・例外内容が出ない」と「他の例外を握りつぶさない」を検証していない(`exc_info=True`・`request.url.path` をログに足す・`except Exception` へ広げる・`except (ClientDisconnect, ValueError, RuntimeError)` へ広げる、の 4 変異が未検出)
- Suggestion: ステータス単位の検査では同じステータス内の `error.code` の取り違えを検出できない(EP-03・04 の 400 から `config_invalid` を落とす等が未検出)/成功ステータス(EP-05・06 の 202 等)の宣言を OpenAPI テストで見ていない/`test_blocking_isolation.py` は Crawler 呼び出しが誤った区分(`opensearch` 等)で実行される退行を検出できない
- Nitpick: `test_tzdata_is_a_direct_dependency` の依存名の分解が壊れやすい/`OPERATIONS` が 6 要素の位置タプル

## 指摘対応

- **README(メインエージェントが直接修正)**: 空文字を未設定として扱うのは `DASHBOARDS_HEALTH_URL`・`EMBEDDING_HEALTH_URL`・`LLM_HEALTH_URL`・`DASHBOARDS_URL`・`CRON_TIMEZONE` だけと明記し、`OPENSEARCH_USERNAME`・`OPENSEARCH_PASSWORD`・`OPENSEARCH_CA_CERTS_PATH` など他の任意変数に空文字を渡しても未設定にはならず設定として検証される(認証情報の片方だけが空文字だと起動に失敗する)と書き直した。URL の検証の説明にフラグメントなしを追記(C 7.3 と揃える)
- **`ClientDisconnect` のテスト強化(test Important)**: WARNING が 1 件・`getMessage()` が固定文・`args` が空・`exc_info is None`・リクエストの path/ID の値がログに出ない(アクセスログ以外の全レコードの `vars()` を確認)。`receive` が `RuntimeError`・`ValueError`・`OSError` を出すと `read_limited_body` から同じ例外がそのまま伝播する(parametrize 3 件)。検出力: `exc_info=True`・path をログに足す→固定文テストが失敗、`except Exception` へ広げる→3 件失敗、`except (ClientDisconnect, ValueError, RuntimeError)` へ広げる→2 件失敗(`OSError` は伝播するため通る)
- **`app.openapi` の差し替えの冪等化(code S1)**: 調整の要否を「FastAPI が返した dict が、調整済みとして記録した dict(`adjusted_schema`)か」で決める。失敗後の呼び出しは調整を再試行し、失敗が続けば呼び出しのたびに同じ例外が伝わる(未調整のスキーマを黙って返さない)。ルートを足して FastAPI にスキーマを再生成させても 422 が復活しない。テスト 4 件(1 回失敗後の 2 回目で 422 なし/失敗が続けば毎回伝播/再生成で 422 が復活しない/キャッシュ中は再調整しない)。旧実装に戻すと 3 件失敗(メインエージェントも差分を確認し、判定の論理に問題なしと判断)
- **`error.code` 単位の突き合わせ(test S2)**: `OPERATIONS` を `ExpectedOperation`(NamedTuple。`operation_id`・`method`・`path`・`tag`・`ok_statuses`・`error_codes`・`request_body`)にし、`error_codes`(ステータス → code 集合)を B 2.3 と各 EP のエラー表から手書き。説明文の `error.code:` の後ろを分解して比較(実装から導出しない)。EP-03・04 の `config_invalid`、EP-02 の 404、EP-10 の 404、EP-03 の 409、EP-05 の `maintenance_enabled`、EP-07 の `job_already_finished` を落とす・替える変異が検出される。重複していた旧テスト 2 件を新テストが包含するため削除
- **成功ステータス(test S3)**: `ok_statuses`(EP-03 は 200/201、EP-07 は 200/202、EP-05・06 は 202、他は 200)を `responses` の 2xx と突き合わせる
- **区分の取り違え(test S4)**: `test_blocking_isolation.py` を、区分ごとの枠をすべて 2 にした `BlockingRunner` で動かして区分共有を顕在化させた。`run(CATEGORY_CRAWLER, …)` を `run('opensearch', …)` に変えると server の読み取りテストと relay 単体(`categories == ["crawler"]`)の両方が失敗。`run("probe", …)` は relay 単体のみ失敗(server 側は `probe` 区分を使わないため検出しない。実害は小さいとして据え置き)
- **`tzdata` のコメント(code Suggestion 2)**: `pyproject.toml` に 2 行(CRON_TIMEZONE の IANA 名の検証に使う・slim イメージに zoneinfo がなくても動く・CalVer なので年初に上限を見直す)
- **Nitpick**: `_too_large()` を `_invalid_body()` に改名して `ClientDisconnect` 分岐でも共有(挙動不変)/`_Unconnected.__getattr__` は `__` で始まる名前だけ `AttributeError`、他は従来どおり `RuntimeError`(テスト 1 件)/`test_tzdata_is_a_direct_dependency` を `packaging.requirements.Requirement` と `canonicalize_name` に置き換え(`packaging` は pytest の依存として `uv.lock` に既にあり、実行・dev 依存は足していない)

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 3410 passed(0017 時点 3389)/ `uv run ruff check`: All checks passed / `uv run ruff format --check`: 249 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし。プロセスの残りなし。`src` の変更は `admin/app.py`・`admin/openapi_export.py`・`common/http/body.py`・`pyproject.toml`(コメントのみ)の 20 行。一時変更の残骸(`if False`・`openapi_schema is None`)なし

## 対応しなかった項目と理由

- code Suggestion 3(`openapi_enabled` の持ち方が二重): 動作に害はない。現状維持
- code Nitpick(Dockerfile のコメント「現時点の `api` は基盤だけ」が古い): 範囲外(Dockerfile は本タスクで変更しない。HO-36 で Dockerfile に触るときに直す)。**設計書追従改訂とは別の申し送り**
- `run("probe", …)` の区分取り違えを server 側で検出しない件: relay 単体が検出する。据え置き

## 申し送りの追加

- Dockerfile(`apps/api/Dockerfile` 11 行目)のコメントが古い(HO-36 で修正)
- `app.py` の docstring に `app.openapi` の再試行方針(失敗が続けば毎回伝播する)を書いた。設計書 D 4.12(c) の追従改訂のとき反映する

## 未対応事項・次にやること

- 再レビュー(Important の解消確認): `test-reviewer`(`ClientDisconnect` のテスト)・`code-reviewer`(README の修正と `app.openapi` の冪等化)。解消後、`task-reviewer`(タスク全体)→ 完了チェックリスト → PR 作成(ユーザー確認のうえ)

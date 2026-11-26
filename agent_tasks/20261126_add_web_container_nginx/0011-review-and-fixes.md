# 0011 レビュー(code-reviewer・test-reviewer)と指摘対応

- 日付: 2026-11-26〜27
- 比較基準: `6569993`。レビュー対象は作業ツリー(未コミット)

## code-reviewer の結果(Critical なし。Important 1)

| 重大度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | `deploy/compose/README.md` が「`crawler` 停止時に約 60 秒で JSON 504」と書いているが、実機で確認したのは `docker pause`(応答しない状態)のみ | **修正**: 「`docker pause`(応答しない状態)にしたとき約 60 秒で…(`stop` した場合は未確認)」に直した |
| Nitpick | `docker compose restart web` は実機未確認(確認したのは `docker restart`) | **修正**: 「`docker restart`(実機で確認。`docker compose restart web` は未確認)」に直した |
| Nitpick | Dockerfile のコメントの `engines` の範囲が実際(`^22.22.2 \|\| ^24.15.0 \|\| >=26`)と違う | **修正**: 「24 系は ^24.15.0」に直した |
| Suggestion | Dockerfile に非 root を採らない判断が書かれていない | **対応**: master は root(80 番のため)、公開は `127.0.0.1` のみ、将来は `nginx-unprivileged`(8080 番)という 2 行のコメントを追加 |
| Suggestion | `proxy_next_upstream off` を明示していない(将来 `api` を複数化したとき、PUT・DELETE が別の `api` に再送されうる) | **見送り**: 単一 `api` の MVP では実害がなく、Nginx 設定を変えると実機の再確認が要る。**申し送り**(`api` の複数化時に入れる) |
| Suggestion | `COPY` が個別列挙なので `public/` などを足し忘れると静かに壊れる | **見送り**: Dockerfile のコメントで注意済み。**申し送り**(フロントの実装タスクで `public/`・`env.d.ts` などを足したら `COPY` も更新する) |

## test-reviewer の結果(Critical なし。Important 1)

| 重大度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | `apps/api/tests/architecture/test_http_rules.py` で `web` と無関係な自己テスト 9 件(R9 の `Depends` 自己テスト 8 件+`test_other_method_names_are_not_probe_calls`)が削除されていた(実装担当が末尾を丸ごと削除したため。0006 にも記載なし) | **修正**: `6569993` から該当の 9 件を原文どおり復元。削除したままにしたのは `web_dist` 例外に直接対応する 2 件(`test_only_the_web_dist_probe_is_called_directly_...`(実ツリーの検査。`test_no_probe_is_called_directly_...` に置換済み)と `test_the_web_dist_probe_may_be_called_directly`)のみ。`git diff 6569993` で、削除された関数がこの 2 件だけであることを確認。`tests/architecture`: 462 passed、`ruff` OK |
| Nitpick | `web` の名前解決失敗(`name_not_resolved`)の over_http テストがない | **対応**: `test_an_unresolvable_host_is_abnormal_name_not_resolved` で `web_url="http://web.invalid:80"` にし、`web` も `("abnormal", "name_not_resolved")` を検査 |
| Nitpick | AIT-93 の読み取り確認の dict が冗長(キー未使用) | **見送り**: `expect_json` が失敗時のメッセージに EP のパスを出すため、実害なし。コメントだけ追記 |
| Suggestion | 7 件の確認すべてが遅い場合の並行(上限 8)のテストがない | **見送り**: 上限 8 は `tests/common/test_concurrency.py` が固定している。**申し送り**として記録 |
| Suggestion | OpenAPI の `ComponentStatus.reason` の列挙(`missing` を含む 6 値)を自動テストで固定していない | **見送り**: 本タスクの必須ではない(OpenAPI の不変は P0・P2 の書き出しの `diff` で確認済み)。**申し送り** |
| Suggestion | Nginx の配信・プロキシと「`api` を publish しない」ことの自動テストがない | **見送り**: 0000・0003 でスコープ外(設計 F 7.1。後続タスクの `tests/integration/<名前>/`)。**申し送り**: `api.ports` の再追加(公開範囲の退行)・`job_id` の `%2F`・`%2E`・本文上限・502・504 を回帰の対象として明記する |

再レビューについて: Important の修正は `6569993` からの原文の復元(機械的)で、`git diff` と `tests/architecture` の実行で確認できるため、test-reviewer への再レビューは省略し、task-reviewer(次工程)で確認対象に含める。code-reviewer の Important は文面の修正のみ。

## 再検証

- `apps/api`: `ruff check`・`ruff format --check` OK、OpenAPI を書き出して変更前と `diff` → 差分ゼロ
- `tests/integration/api`: `ruff check`・`ruff format --check` OK、`pytest --collect-only` 24 件
- `docker build apps/web`(Dockerfile のコメント変更後): 成功
- `apps/api` の全体 `pytest`: **3435 passed**(100 秒。復元した 9 件・追加した検査を含む)
- IT は再実行していない(IT 側の変更は `test_90` のコメント 1 行のみ。0008 の 24 passed の後に変えたのはこのコメントだけ)

## 変更ファイル(この工程)

`deploy/compose/README.md`、`apps/web/Dockerfile`(コメント)、`apps/api/tests/architecture/test_http_rules.py`(9 件を復元)、`apps/api/tests/admin/routers/test_dashboard_over_http.py`(`web` の名前解決失敗)、`tests/integration/api/test_90_component_failures.py`(コメント)

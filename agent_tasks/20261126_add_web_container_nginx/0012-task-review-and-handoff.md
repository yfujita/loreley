# 0012 タスクレビューと最終の申し送り

- 日付: 2026-11-27
- 承認の経緯: プラン(0003)は 2026-11-26 にユーザーが承認した(承認の記録は 0004)

## task-reviewer の結果

完了条件 13 項目のうち 12 項目が ○(作業記録の根拠と実ファイルが一致)、13(未対応事項の記載)は本記録で満たす。Critical なし。

| 重大度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | `tests/integration/api/README.md:138` に古い「23 テスト」が残っている(43 行目は 24) | **修正**: 「24 テスト(AIT-11 のパラメータ 2 件と AIT-93 を含む)」に直した |
| Suggestion | `ComponentId` の docstring の扱いをユーザー確認事項として明示する | 下記「ユーザーに確認したい点」に記載 |
| Suggestion | `test_a_direct_call_of_another_probe_is_detected` も期待値が変わっている(`self._web_probe` も違反として検出する)。0011 に記載なし | 記録(`web_dist` 例外に直接対応する妥当な変更) |
| Suggestion | 設計の仮値と最終値の対比 | 下記「Nginx の最終値」に記載 |
| Suggestion | 未実測の列挙 | 下記「未実測・未実施」に記載 |
| Nitpick | 0003 冒頭が「承認待ち」のまま / STATUS の文言 | 0003 は書き換えない運用。承認は 0004 と本記録に記載。STATUS は完了時に整理した |

## 確定した値(設計 E 3.3 の仮値との対比)

| 項目 | 最終値 | 設計の仮値との差 |
| --- | --- | --- |
| `proxy_connect_timeout` | 5s | 変更なし |
| `proxy_send_timeout` | 30s | 変更なし(仮値) |
| `proxy_read_timeout` | 90s | 要件の「90 秒以上」を満たす(api の Crawler 待ち約 63 秒より長い。実測で JSON 504 が約 60 秒で返ることを確認) |
| `client_max_body_size` | 2m | api の上限 1 MiB より大きい。1 MiB+1 は api の JSON 400、2 MiB+1 は Nginx の HTML 413 |
| gzip | `/admin/assets/` の location 内のみ・設計 3.3 の 5 種・`gzip_min_length 1024`・**`gzip_vary on` を追加** | `server` 全体ではなく assets のみ(`/api/` の JSON を圧縮しないため)。`gzip_vary` は追加 |
| `resolver` | `127.0.0.11 valid=10s ipv6=off` | — |
| `Host` | `$http_host` | — |
| `add_header` | location ごと・`always` なし(404 に `Cache-Control` なし) | — |
| セキュリティヘッダー(CSP 等)・`/healthz`・`/favicon.ico` | 置かない | — |

- 環境変数: `LORELEY_API_WEB_URL`(必須。`http` のみ・パス/クエリなし。compose の値は `http://web:80`)。確認先は `{WEB_URL}/admin/`(`dashboard.py` の `WEB_HEALTH_PATH`。末尾スラッシュ必須: `HttpHealthProbe` がリダイレクトに従わないため)
- `web` の healthcheck: イメージの `HEALTHCHECK`(`wget -q -O /dev/null http://127.0.0.1/admin/`、interval 15s)
- `WEB_HOST_PORT` の既定値: 8090(IT でも固定。compose のマージは `ports` を消せないため。IT の固定ポートは 9200・8000・8001・8080・8090 の 5 つ)
- イメージ: `node:24.22.3-bookworm-slim`・`nginx:1.30.8-alpine`(stable。設計 0005 の確認は mainline 1.31.10 だが、同じ設定が 1.30.8 でも通ることを確認)。いずれもタグ+ダイジェスト固定(2026-11-26)

## ユーザーに確認したい点

1. **`ComponentId` の docstring を直さなかった**: 0000 は「docstring を直す」と「OpenAPI 差分なし」の両方を求めているが両立しない(docstring は OpenAPI の `description` に出る)。0003 の P-4 は「直す」としていたが、完了条件(OpenAPI 不変)を優先して直さず、クラス内に理由のコメントを残した(0006)。プランから外れた判断なので確認してほしい。直す場合は OpenAPI の更新(と生成型の再生成)を伴う別タスクになる。あわせて `ProbeReason` の `"missing"`(返す確認がなくなったが、OpenAPI 互換のため残した)の廃止も同じ別タスクで扱う
2. **コミット・PR**: P-10 のとおり未コミット。B と C は同じコミット範囲で扱う(ロールバックも同様)。ステージ済みの削除が 2 件ある(`git rm` 由来: `test_web_dist.py`・`fixtures/web/index.html`)

## 未対応事項・申し送り

**設計書・文書の追従改訂(別タスク。HO-59・60・65)**
- `docs/v0.x/system-design/api/admin/` の `admin-api-architecture-v0.1.md`(7.2 の環境変数表の `WEB_DIST_DIR`・6.3 の `web` 判定・10 章の HO-35・36・R9 の例外)・`admin-api-module-structure-v0.1.md`・`admin-api-v0.1.md`、`api/api-base-design-v0.1.md`(HO-59・60・65、FARC-U-6・21 と HO-53〜58 の状態、IT の固定ポートが 5 つになったこと(HO-56 の補足))、`ui-admin/frontend/` の architecture v0.1・v0.2 と module-structure v0.2(E 3.3・3.6・12.4)
- 設計に反映する値: `LORELEY_API_WEB_URL`(必須・確認先 `/admin/`)、`web` の healthcheck、`WEB_HOST_PORT=8090`、Nginx の最終値(上表)、Node・Nginx のイメージ(Nginx は stable 1.30.8)
- IT 結果文書 `docs/v0.x/test-results/admin-api-integration.md`(24 テスト・AIT-93・`[observed]` の `name_not_resolved`・実行環境の追記)と、`tests/integration/api/README.md` 7 行目の確認状況(「23 passed」)

**Nginx・compose まわり(見送り)**
- `proxy_next_upstream off`(`api` を複数化するとき)
- `COPY` の個別列挙: フロントの実装タスクで `public/`・`env.d.ts` などを足したら `apps/web/Dockerfile` の `COPY` も更新する
- セキュリティヘッダー(CSP など)と `/favicon.ico` の 404(コンソールエラーの原因。Search View の置き場と合わせて検討)
- 非 root 化(`nginx-unprivileged`、8080 番)は将来の検討
- compose v2.3.3 の挙動: `up -d --no-deps --force-recreate web` が `depends_on` の `api` も起動する(0009)。README の手順に載せていない

**テストの見送り**
- 確認 7 件がすべて遅い場合の並行(上限 8)のテスト
- OpenAPI の `ComponentStatus.reason` の列挙(`missing` を含む 6 値)を固定するテスト
- Nginx・compose の自動テスト(後続の `tests/integration/<名前>/`。設計 F 7.1)。回帰の対象として次を明記する: `api.ports` の再追加(公開範囲の退行)、`job_id` の `%2F`・`%2E`、本文上限(400/413)、`api` 停止中の 502、約 60 秒の JSON 504、`/admin/` の配信・SPA・assets 404・301/302

**未実測・未実施**
- 任意項目 11(`npm run dev` → `web` → `api` の連鎖。設計 3.4 の未確認点。フロントの実装タスクで)
- HTML の 504(`proxy_read_timeout` 超過)の実測、`crawler` を `stop`(`pause` ではなく)したときの `api` の応答、`docker compose restart web`
- IT は 0008 の 1 回(24 passed、442 秒)。その後の IT 関連の変更は `test_90` のコメントのみ

**運用上の案内**
- `.env` の `API_HOST_PORT` は不要になった(IT の上書き用のみ)。`WEB_HOST_PORT` を使う
- `docker compose up -d --build` は `web` のビルドで npm レジストリへの接続が要る。`api` の必須環境変数が 4 つになった(`LORELEY_API_WEB_URL`。compose では設定済み)
- `api` の確認は `docker compose ps`・`docker compose logs web api`・`docker compose exec api python -c ...`

## 完了チェックリスト

- [x] プランが作業記録(0003)に残り、ユーザーの承認を得ている(0004)
- [x] すべての作業に作業記録がある(0002〜0012)
- [x] プランで指定されたレビュー(code-reviewer・test-reviewer・task-reviewer)を実施。`web-ui-reviewer` は省略(画面・スタイルの変更なし。0003 の 5 章)。test-reviewer の再レビューは、機械的な復元のため省略し task-reviewer で確認(0011)
- [x] 未対応事項を最新の作業記録(本記録)に書いた
- [x] `STATUS.md` を最新の作業記録と一致させた

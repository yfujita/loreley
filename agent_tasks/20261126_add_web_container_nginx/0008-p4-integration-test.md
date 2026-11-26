# 0008 P4: 結合テスト(IT)の追従と実行

- 日付: 2026-11-26
- 実施: code-implementer(実装のみ)→ メインエージェントが IT を実行

## 変更ファイル

- `tests/integration/api/compose.test.yaml`: `api.volumes`(/app/web の mount)を削除。`api.ports: "127.0.0.1:${API_HOST_PORT:-8080}:8080"` を追加(crawler と同じ診断・テスト用の上書き。本番用には書かない)。`web.healthcheck.interval: 3s` を追加(test・start_period はイメージのもの)。冒頭コメントを更新
- `tests/integration/api/fixtures/web/index.html`: 削除(`fixtures/` ごとなくなった。`git rm` によりステージ済みの削除が 1 件ある)
- `tests/integration/api/support.py`: `CONTROLLABLE_SERVICES` に `web`、`SERVICES_TO_AWAIT_AFTER_START` に `"web": ("web",)`。コメント・docstring を更新
- `tests/integration/api/test_01_startup.py`: docstring のみ(実 `web` を api が `http://web:80/admin/` で確認する前提。アサーションは不変)
- `tests/integration/api/test_90_component_failures.py`: **AIT-93 を追加**(`test_web_down_marks_only_the_web_component_abnormal_and_recovers`)。`compose_control.stopped("web")` の区間で EP-13 の `web` が abnormal(`reason` は `connection_refused` か `name_not_resolved`)・他は normal・任意の 3 つは `not_configured`、読み取り EP-01・09・12・14 と `/healthz` が 200。復旧後に 5 つが normal。モジュール docstring・安全策の記述も更新
- `tests/integration/api/conftest.py`: docstring の前提に `web` を追加(記述のみ。依頼範囲外だが軽微)
- `tests/integration/api/README.md`: ポート 5 つ、`web` のビルドが前提(npm レジストリ接続が要る)、AIT-93、fixtures と `/app/web` の記述の撤去、シナリオ数(24 テスト)
- `scripts/run-api-integration-test.sh`: `WEB_PORT=8090`・`export WEB_HOST_PORT`・`IT_PORTS`・`IT_SERVICES`(`web`)・`IT_WAIT_CHECKS`(`web:healthy`)・ヘッダーコメント(8090 を固定する理由)。`scripts/lib/it-common.sh` は不変(crawler・indexer の IT は `web` を `IT_SERVICES` に含めず影響なし)

## 検証

- `bash -n`、`ruff check`・`ruff format --check`(`tests/integration/api`)OK。`docker compose config` で api が `127.0.0.1:8080`、web が `127.0.0.1:8090`、api の volumes に `/app/web` なし
- `grep -rn "web_dist\|WEB_DIST\|/app/web\|fixtures/web" tests scripts`(`results/` の過去ログを除く): 0 件
- **IT 実行**(`scripts/run-api-integration-test.sh`。事前に 5 ポートが空き、実行中のコンテナ・排他ロックなしを確認): **24 passed(442.59 秒)**、終了コード 0。後始末(`down -v`・data/ 削除・ロック解除)も完了。実行前から存在した停止中の `opensearch-opensearch-1` には触れていない
- 観測値(`[observed]`): **AIT-93 EP-13 web reason: `name_not_resolved`**(AIT-90・91・92 の各 reason も `name_not_resolved`。従来と同じ)

## 未対応・次の作業

- `docs/v0.x/test-results/admin-api-integration.md` と IT README 冒頭の「確認状況」(過去の「23 passed」)の更新要否は未判断。結果ドキュメントの更新は設計書・文書の追従改訂の申し送りに入れる(本タスクのスコープ外)
- P5(実機確認)へ

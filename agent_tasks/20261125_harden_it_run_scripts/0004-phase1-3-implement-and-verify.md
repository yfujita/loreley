# 0004 Phase 1〜3: 共通ファイルの実装・3 本の移行・Docker を使わない検証

日付: 2026-11-26 / 実装: `code-implementer` / 検証: メインエージェント(実装の報告を鵜呑みにせず、Phase 3 で独立に再確認)
基準: コミット `96a9b52`(0003)。コミットはしていない。

## 実施内容(Phase 1〜2)

- `scripts/lib/it-common.sh`(559 行、新規)を作成。shebang・実行権限なし。定数、`error`/`info`/`compose`、`parse_common_args`、`acquire_lock`/`release_lock`/`report_lock_unavailable`、事前確認一式、`print_diagnostics`、`cleanup_stack`、`on_exit`、`probe_service`/`wait_for_stack`、`run_integration_test`
- 3 本(api 111 行・crawler 106 行・indexer 110 行。もとは 473/433/326 行)を共通ファイルへ移行
- Crawler・Indexer への反映: `LORELEY_IT_*_URL` の固定、`docker ps -a`・`docker volume ls` 失敗時の中止、`data/` の存在確認と一覧取得の分離(Crawler)、後始末失敗の終了コード 11。Indexer に残骸確認(コンテナ・ボリューム)とポート使用中の相手の表示を追加
- ヘッダコメント(`--help` の出力)を更新: 終了コード 1・11 の説明、ロック、固定する値(Crawler・Indexer)、Indexer の `down -v` の安全確認

### 0002 からの逸脱(実装者の報告。いずれも小さく、メインエージェントが妥当と判断)

1. `cleanup_stack` を `on_exit` から分けた(`on_exit` は終了コードを控え、armed なら `cleanup_stack`、次に `release_lock`、最後に 11 の判定)
2. `release_lock` は、保持者の PID が自分と違うとき、消さずに警告して 0 を返す(相手のロックを消さないのが目的で、自分の後始末の失敗ではないため。終了コード 11 にしない)。`owner` が空・PID 行なしのときは、書き込み失敗直後の自分のロックとみなして解除する
3. `lock_acquired`・`stack_cleanup_armed`・`wait_timeout_secs`・`keep_stack`・`pytest_args` の初期値は、共通ファイルの先頭で定義
4. `LORELEY_IT_WAIT_TIMEOUT_SECS` の検証は `parse_common_args` の中(順序は元のまま)
5. `owner` を書けなかったときは `exit 1`。`lock_acquired=true` を先に立てるので、`on_exit` が解除する

## 検証(Phase 3 相当を含む)

### 偽の `docker`(リポジトリには入れない。スクラッチパッドの `fake-docker/docker`)

```bash
#!/usr/bin/env bash
# 検証専用。指定した 1 種類の呼び出しだけを失敗させ(または待たせ)、それ以外は本物の docker に渡す。
set -u
real="${FAKE_DOCKER_REAL:?本物の docker の絶対パスを指定する}"
has_arg() { local a; for a in "${@:2}"; do [ "$a" = "$1" ] && return 0; done; return 1; }
case "${FAKE_DOCKER_MODE:-}" in
  fail-ps-a)         [ "${1:-}" = ps ] && has_arg -a "$@" && { echo "fake: docker ps -a を失敗させた" >&2; exit 1; } ;;
  fail-volume-ls)    [ "${1:-}" = volume ] && [ "${2:-}" = ls ] && { echo "fake: docker volume ls を失敗させた" >&2; exit 1; } ;;
  fail-compose-down) [ "${1:-}" = compose ] && has_arg down "$@" && { echo "fake: compose down を失敗させた" >&2; exit 1; } ;;
  hang-info)         [ "${1:-}" = info ] && exec sleep 120 ;;
esac
exec "$real" "$@"
```

使い方: `PATH="<fake-dir>:$PATH" FAKE_DOCKER_REAL="$(command -v docker)" FAKE_DOCKER_MODE=<mode> scripts/run-*.sh`

### 結果(すべて期待どおり)

| # | 内容 | 結果 |
| --- | --- | --- |
| 静的 | `bash -n` と `/bin/bash`(3.2.57)での `bash -n`(4 ファイル) | OK |
| 静的 | `--help` を baseline と diff | 差分は意図したヘッダの更新だけ。3 本とも終了コード 0。実行権限 755 を維持 |
| 静的 | shellcheck | **未実施**(ホストに無い) |
| 1 | `fail-ps-a`(api・crawler・indexer) | 3 本とも終了コード 1、「docker ps に失敗しました。残骸の有無を確認できないため中止します。」。コンテナ・ボリューム・`data/` は作られず、終了後にロックなし |
| 2 | `fail-volume-ls`(crawler・indexer・api) | 3 本とも終了コード 1、「docker volume ls に失敗しました。」。結果は 1 と同じ |
| 3 | Crawler の `data/` を `chmod 000` | 終了コード 1、「内容を確認できませんでした(権限など)。削除してよいか判断できないため中止します。」。`data/` は残り(利用者のデータを消さない)、ロックなし。検証後に権限を戻して削除 |
| 4 | `hang-info` で起動 → `kill -9`(子の `sleep` も停止) | ロックが残った。次の Crawler の実行(本物の docker)は終了コード 1 で、保持者の PID(30443、kill したものと一致)・開始時刻・スクリプト名、`ps -p`・`rm -rf` の手順を表示し、何も消さなかった。手動で `rm -rf` した後の `fail-ps-a` 実行はロックを取って中止し、終了後にロックなし |
| 5 | 先発(Indexer、`hang-info`)の実行中に、後発(api)を起動 | 後発は終了コード 1 で保持者(先発の PID・スクリプト名)を表示。**後発の後も先発のロックは残っていた**(相手のロックを消さない)。先発に INT(子の `sleep` にも送る。Ctrl-C 相当)→ 終了コード 130、ロックなし |
| 5' | TERM(api、`hang-info`) | 終了コード 143、ロックなし、`sleep` の残りなし |
| 6 | `--help`(3 本) | 終了コード 0、ロックを作らない |
| 追加 | `LORELEY_IT_WAIT_TIMEOUT_SECS=abc`(3 本)、`=0`(Crawler)、Indexer の `LORELEY_IT_PYTEST_CMD="  "` | 終了コード 1、ロックを作らない(実装者が確認。メインエージェントは再確認していない) |
| 追加 | 共通ファイルが無い状態で `--help` | 「共通ファイルが見つからないか、読めません」で終了コード 1(実装者が確認。メインエージェントは再確認していない) |

各検証の前後で、`loreley-it` のコンテナ 0・ボリューム 0・`data/` なし・ロックなしを確認した。他プロジェクトのコンテナ(`opensearch-opensearch-1`)は変化なし。

## 未実施・未検証(Phase 5 で確認する)

- Docker のスタックを実際に起動する経路: `on_exit` の全経路、`--keep`、`down -v` 失敗時の終了コード 11、Indexer の残骸検出、`up` から pytest までの流れ、全件実行
- `pytest_args` が空のときの `${pytest_args[*]:+ ...}` 展開(`set -u`・bash 3.2)は、pytest 起動まで進む Phase 5 で確認する
- shellcheck は未実施。実行できる環境があれば、各スクリプトの `IT_*`・`pytest_cmd` が共通側でしか使われないことによる SC2034 の警告が出る可能性が高い(`--help` の出力を変えないよう、ヘッダに `disable` 指示は入れていない)
- 既知のリスク(0002 に記載): `mkdir` の成功から `lock_acquired=true` までの間にシグナルを受けるとロックが残る(手動解除)

## 次のアクション

1. Phase 4(R1): `code-reviewer`(必須)と `test-reviewer` を並列で実行する
2. Critical・Important を解消した後、Phase 5(Docker を使う検証・全件実行)へ

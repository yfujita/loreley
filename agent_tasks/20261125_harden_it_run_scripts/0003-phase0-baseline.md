# 0003 Phase 0: 基準の記録

日付: 2026-11-26 / 実施: メインエージェント / プラン(0002)はユーザー承認済み

## 基準

- 基準コミット SHA: `96a9b52a57fbc36a3b881791b167e9ad12de7ed8`(ブランチ `main`)
- 作業ツリー: `agent_tasks/20261125_harden_it_run_scripts/` が未追跡のみ。スクリプト・README・結果文書は未変更
- ブランチは作成していない(コミットはユーザーから指示があったときに、その時点で作る)

## 実行前のホストの状態

- `docker ps -a` 全体: `opensearch-opensearch-1`(Exited (143) 2 weeks ago、プロジェクト `opensearch`)の 1 件のみ。**このコンテナには触れない**
- `docker volume ls`: `opensearch-data`、`opensearch_opensearch-data`(プロジェクト `opensearch`)。どちらも `loreley-it` のものではない
- `loreley-it` のコンテナ 0 件、ボリューム 0 件
- ロック `${TMPDIR}/loreley-it.lock`: なし(`TMPDIR=/var/folders/rp/t0y91r657plfrbx4p338vw_00000gn/T/`)
- `tests/integration/*/data`: なし
- ポート 9200・8000・8001・8080: すべて空き
- `shellcheck`: 見つからない(`bash -n` で代替し、未実施と明記する)
- `/bin/bash`: GNU bash 3.2.57(bash 3.2 互換の確認が必要)

## 比較用に保存したもの(スクラッチパッド `baseline/`)

- `docker-ps-a.txt`、`volumes.txt`
- `help-{api,crawler,indexer}.txt`(`--help` の出力。api 40 行、crawler 31 行、indexer 32 行。いずれも終了コード 0)

## 未対応事項・次にやること

- Phase 1〜2: `code-implementer` が `scripts/lib/it-common.sh` を作り、3 本を移行する

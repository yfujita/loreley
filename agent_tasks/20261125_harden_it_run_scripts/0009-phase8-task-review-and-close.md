# 0009 Phase 8: タスクレビューの結果と完了処理

日付: 2026-11-26 / レビュー: `task-reviewer`、`test-reviewer`(再レビュー)/ 対応: メインエージェント
基準: コミット `96a9b52`。**コミット・PR はしていない**(ユーザーの指示を待つ)。

## task-reviewer の結果

判定: 完了としてよい(Critical なし、Important 1 件。作業記録への追記のみで解消)。0001 の要件 1〜7・完了条件 1〜6 は、実物と作業記録の証拠で満たされている(shellcheck のみ「未実施」と明記して許容)。`bash -n`・ログ最終行(14/40/23 passed)・残骸なし・結果文書が追記のみ・変更範囲が `scripts/`・README・結果文書に限られることを、レビュアー自身が確認した。

| 指摘 | 対応 |
| --- | --- |
| Important: `test-reviewer` の Important 6 件(I1〜I6)について、プラン(0002 の 6 章)が求める再レビューの扱いが記録されていない | **再レビューを実施した**(省略しなかった)。`test-reviewer` に 0005・0006・ログ実物を渡して確認させ、**I1〜I6 はすべて解消**(I6 は INT の「準備完了後」が未実施だが、INT と TERM は同じ `exit` への変換で、INT は準備完了前を 0004 で確認済みのため許容)。Critical・Important は残っていない |
| Suggestion: 0000 の To-Be「ロックは異常終了後に残り続けない」と、確定した Q3(SIGKILL 等で残ったロックは自動では消さず手動解除)の食い違いが STATUS.md の未解決事項にない | **STATUS.md の未解決事項に追加**(ユーザー判断事項) |
| Suggestion: 作業記録の「確認の範囲」(`data/` の不変、ロック解除失敗の 11) | 下の「確認の範囲」に記載。ロック解除失敗の 11 は、結果文書 3 つの静的検査の節にも 1 行追記(下記) |
| Suggestion: document-reviewer の Important 修正で再レビューを省略 | 0008 に理由を記録済み(文言のみの修正で、`grep`・`git diff --numstat` で反映と追記のみを確認。レビュアー自身も反映を実物で確認)。対応不要 |
| Suggestion: `release_lock` の PID 不一致で 0 を返す判断 | 妥当(記録・README とも明示)。対応不要 |
| Nitpick: ヘッダの「(下の「排他ロック」)」という存在しない見出しへの参照 | **修正**。3 本のスクリプトのヘッダコメントから削除(コメントのみ。`bash -n`・`--help` の終了コード 0 を確認) |
| Nitpick: README の「別の clone・worktree で起動した実行とも排他される」は実測していない | 見送り。ロックが `TMPDIR` にあることの論理的な帰結(clone・worktree の実測はしていない)。必要なら文言を弱める(ユーザー判断) |

## `test-reviewer` の再レビューで追加された指摘への対応

- Suggestion S1(結果文書に、ロック解除失敗の 11 の確認範囲が書かれていない): **修正**。結果文書 3 つの静的検査の節(crawler 9.3、indexer 10.3、admin-api 10.3)に、「ロックの解除に失敗したときに終了コード 11 になる経路は、`scripts/lib/it-common.sh` を `source` した関数レベルの確認だけで、スクリプトを通した実機の再現はしていない」を 1 行追記(追記のみ。削除行 0)
- Suggestion S2(5-5 の 2 本目は pytest 実行中に起動した): 0006 には「準備完了後」と書いてあり、事実と一致している。結果文書の記述も同じ。対応不要
- Nitpick N1・N2: 事故の記録は 0005 のとおり。判定の grep はテスト名に誤ヒットするが、0006 の判定結果(skip なし)自体は正しい

## 確認の範囲(正直な記録)

- 実スタックで確認したもの: Crawler・Indexer の終了コード 11 と URL 固定、Indexer の残骸検出(コンテナ・ボリューム)、Crawler・Indexer の `--keep`、Indexer の TERM、同時実行の拒否(Crawler 実行中に Indexer・Crawler・api の 3 本)、3 本の全件実行(14/40/23 passed)
- 偽の `docker`・旧新比較・関数レベルで確認したもの: `docker ps -a`・`volume ls` の失敗、空でない `data/`・`chmod 000`、ポート占有(全 9 ポート)、`kill -9` で残ったロックの案内と手動解除、INT・TERM(準備完了前)、ロック競合 10/10、uv の有無、引数エラー、共通ファイル欠落、ロック解除失敗の 11(関数レベルのみ)
- `data/` の不変そのものは直接比較していない(同時実行の拒否の検証では、コンテナ ID・ボリューム・`StartedAt` の不変、`docker events`、1 本目の 14 passed から判断した。2 本目は準備完了前に中止し、`data/` を触る経路に到達しない構造であることをコードで確認)
- 実スタックでは未実施: api の `--keep`・残骸検出・TERM、Crawler の INT・TERM、INT の準備完了後。いずれも共通コードを他の IT で確認済みのため、許容
- 未実施: **shellcheck**(ホストに無い。`bash -n`・`/bin/bash` 3.2.57 の `bash -n` は 4 ファイルとも OK)。Linux ホストでの実行
- 実装者の報告とメインエージェントの再確認の区別: 0004 で「実装者の確認のみ」としていた項目は、0005 の 3-H でメインエージェントが再確認した

## プランからの乖離の一覧

- 実装者の逸脱 5 件(0004)。いずれも小さく、記録済み
- Phase 3 の検証を、test-reviewer の指摘(0005)で拡張し、Phase 5 の手順に追記(0005 の 4 章)
- 事故(0005 の 5 章): 追加検証のハーネスのバグで、本物のスタックが 1 度起動し、その後の強制終了で `loreley-it` のスタックとロックが残った。`loreley-it` のものだけを確認して片付けた。他プロジェクトへの影響なし
- R1 の `code-reviewer` の再レビューは省略(文言 1 行の修正。0005 に理由を記録)。R2 の `document-reviewer` の再レビューも省略(文言のみ。0008 に理由を記録)。R1 の `test-reviewer` は再レビューを実施した(本記録)

## 完了チェックリスト(`.claude/rules/task-workflow.md`)

- [x] プランが作業記録(0002)として残り、ユーザーの承認を得ている(0003 に承認済みと記録)
- [x] すべての作業に作業記録がある(0001〜0009。連番に欠落・重複なし。Phase 1〜3 は 0004 に統合)
- [x] プランで指定されたレビュー(R1: code-reviewer・test-reviewer、R2: document-reviewer、Phase 8: task-reviewer)を実施。省略した再レビューは理由を記録
- [x] 未対応事項を最新の作業記録(本記録)に書いている
- [x] `STATUS.md` が最新の作業記録と一致している(状態 `done`、最新作業記録 0009)

## 未対応事項(ユーザー判断・今後)

- **コミット・PR**: 未実施(ユーザーの指示があってから)。基準 SHA `96a9b52`。変更ファイルは `scripts/lib/it-common.sh`(新規)、`scripts/run-{api,crawler,indexer}-integration-test.sh`、`tests/integration/{crawler,indexer,api}/README.md`、`docs/v0.x/test-results/{crawler,indexer,admin-api}-integration.md`、`agent_tasks/20261125_harden_it_run_scripts/`
- 0000 の As-Is(14 行目)が Indexer の現状と合わない件、対象範囲に結果文書がない件、To-Be の「ロックは異常終了後に残り続けない」と Q3 の確定内容(手動解除)の食い違い: 0000 を直すかはユーザー判断(0001 で補った)
- 各 README 冒頭の「確認状況」の注記(日付・件数)の更新: ユーザー判断
- shellcheck: 使える環境で実行する(SC2034 の警告が出る可能性が高い。ヘッダの `set -euo pipefail` の後ろに `# shellcheck disable=SC2034` を置けば `--help` の出力は変わらない)
- 既知のリスク: `mkdir` 成功から `lock_acquired=true` までのシグナルでロックが残る(手動解除。README に記載)
- 見送ったレビュー指摘: `on_exit` 中の 2 回目のシグナル、`mkdir` 失敗後の TOCTOU の表示、`owner` の無加工表示、README の構成の差

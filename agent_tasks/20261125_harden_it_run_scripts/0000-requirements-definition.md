# 20261125_harden_it_run_scripts

(PR #19 の外部レビューで別タスクとした項目をもとに、メインエージェントが起こした下書き。2026-11-26 に、ユーザーの指示で、要件確認(0001)で確定した内容に合わせて修正した。修正した箇所: 現状(As-Is)の Indexer の記述、あるべき姿(To-Be)のロックと共通化、具体的にやること、対象範囲、完了条件)

## 背景・目的

Admin API IT の実行スクリプト(`scripts/run-api-integration-test.sh`)は、PR #19 のレビュー指摘(接続先 URL の固定、事前確認のエラー処理、後始末失敗の終了コード)を反映済み。一方、同じ土台から作られた Crawler IT・Indexer IT の実行スクリプトには同じ問題が残っている。また、3 本のスクリプトは同じ Compose プロジェクト名(`loreley-it`)とポートを使うが、同時実行を確実には拒否できない。安全性に関わる修正を 3 ファイルへ個別に反映する状況を解消し、IT 基盤の安全性を揃える。

## 要件

### 現状(As-Is)

- `run-crawler-integration-test.sh`・`run-indexer-integration-test.sh` は、テストの接続先 URL(`LORELEY_IT_*_URL`)を固定していない。シェルに残った環境変数で、別の環境に書き込むおそれがある
- Crawler の事前確認は、`docker ps -a` の失敗や `data/` の一覧取得の失敗を「残骸なし」と扱う可能性がある(`|| return 1` の文脈で `set -e` が効かない)
- Indexer の事前確認には、コンテナ・ボリュームの残骸確認がそもそもなく(ポート使用中の確認だけ)、終了時の `down -v` が、前回 `-v` なしで止めたボリュームを黙って消すおそれがある
- 両スクリプトは、テストが成功しても後始末(`down -v`、Crawler は `data/` の削除も)に失敗すれば終了コード 0 を返す(api IT は修正済みで、終了コード 11)
- 3 本の事前確認は排他ではない。両方が事前確認を通過すると、一方の後始末で他方の環境が消えるおそれがある
- 事前確認・起動待機・後始末の実装が 3 本で重複している(api IT は約 450 行)

### あるべき姿(To-Be)

- 3 本とも、接続先 URL の固定・事前確認の安全側の失敗処理・後始末失敗の終了コードが api IT と同じ方針になっている
- Indexer にも、api・Crawler と同じコンテナ・ボリュームの残骸確認とポート使用中の相手の表示が入っている
- 3 本の IT は、共通の排他ロックで同時実行を確実に拒否できる。ロックは、通常の終了と INT・TERM では必ず解除される。SIGKILL・電源断などで残ったロックは、自動では解除せず、保持者の情報を表示して中止し、手動で解除する手順を案内する
- 重複している実装が共通の関数ファイル(`scripts/lib/`)にまとめられ、今後の安全性修正を 1 か所で済ませられる

### 具体的にやること

- Crawler IT・Indexer IT の実行スクリプトに、api IT で入れた 3 点の修正を反映する(`LORELEY_IT_*_URL` の固定、`docker ps` 失敗時の中止、`data/` の存在確認と一覧取得の分離(`data/` がある IT のみ)、後始末失敗時の終了コード)。Indexer には、残骸確認(コンテナ・ボリューム)とポート使用中の相手の表示を追加する
- 3 本共通の排他ロックを実装する(`mkdir` の原子性を使うロックディレクトリ。macOS・Linux 互換。置き場所は `${TMPDIR:-/tmp}/loreley-it.lock`。残ったロックは自動では解除せず、手動の解除手順を案内する)
- 共通の関数ファイルを `scripts/lib/` に作り、3 本から `source` する(IT ごとの違いは各スクリプトの変数で渡す)
- 各 IT の README・結果文書を更新する

## 対象範囲

- `scripts/run-crawler-integration-test.sh`、`scripts/run-indexer-integration-test.sh`、`scripts/run-api-integration-test.sh`(排他ロック・共通化の反映)
- `scripts/lib/` 配下の新規の共通シェルファイル
- `tests/integration/{crawler,indexer,api}/README.md` の該当記述
- `docs/v0.x/test-results/{crawler,indexer,admin-api}-integration.md`(再実行の記録の追記のみ)

## スコープ外

- `apps/` のアプリケーションコード、IT のテストケース自体の追加・変更
- Compose 定義(`deploy/compose/`)の変更
- IT を CI で実行する仕組み
- 3 つの IT を並行実行できるようにすること(別プロジェクト名・別ポート)

## 制約・前提条件

- 他プロジェクトのコンテナ(例: `opensearch-opensearch-1`)や、ユーザーのデータを消さない。事前確認は安全側に倒す
- 変更後も、Crawler IT(14 件)・Indexer IT(40 件)・api IT(23 件)が従来どおり成功する
- 排他ロックは `flock` などの Linux 専用コマンドに依存せず、macOS でも動く
- ホストがスリープすると IT が失敗しうる(`caffeinate -i` で実行する)

## 完了条件

- [x] 3 本の実行スクリプトが、接続先 URL の固定・事前確認の失敗処理・後始末失敗の終了コードで同じ方針になっている
- [x] 2 つの IT を同時に起動しようとしたとき、後から起動した側が何も消さずに中止することを実際に確認している
- [x] 異常終了後にロックが残った場合の扱い(手動で解除する手順を案内。自動解除はしない)が決まり、README に書かれている
- [x] 3 つの IT が修正後に成功し、実行後に残骸がない
- [x] shellcheck が使えるなら実行する。使えなければ未実施と明記する(ホストに無く未実施。結果文書に明記)

(チェックは、2026-11-26 のタスクレビュー(0009)の結果に基づく)

## 成果物

- 修正後の実行スクリプト 3 本と共通ファイル(`scripts/lib/`)
- 更新した README・結果文書・作業記録

## 補足・参考情報

- 元の指摘: PR #19 レビュー(1-2 排他制御、3-3 実行スクリプトの共通化)。対応済みの内容は `agent_tasks/20261125_create_it_for_admin_api/0014-pr19-review-fixes.md`
- 修正の実装例: `scripts/run-api-integration-test.sh`(`check_no_leftover_stack`・`check_no_leftover_data`・`cleanup`)

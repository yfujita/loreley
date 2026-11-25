# 0005 Phase 4(R1): コード・テストレビューの結果と対応、追加の Docker なし検証

日付: 2026-11-26 / レビュー: `code-reviewer`・`test-reviewer`(並列)/ 対応・検証: メインエージェント
基準: コミット `96a9b52`(0003)。コミットはしていない。

## 1. code-reviewer の結果

Critical・Important なし(判定: 可)。事前確認、trap とフラグ、終了コード、ロック、bash 3.2、api の挙動、0001 に無い機能の混入、のいずれも問題なし。

| 指摘 | 内容 | 対応 |
| --- | --- | --- |
| Suggestion 1 | `release_lock` が、保持者の PID が違うとき警告のみで 0 を返す。利用者が実行中のロックを誤って手動解除すると、排他が破れても成功(0)で終わる | **現状維持**(MVP)。相手のロックを消さないのが目的で、0002 の決定どおり。README に「手動解除を誤ると警告のみで終わる」ことを書く(Phase 6) |
| Suggestion 2 | `on_exit` の最中に 2 回目の INT・TERM を受けると、後始末の途中で死んで残る | **見送り**。0001 に無い挙動の追加。移行前から同じ性質(ロックが加わっただけで、案内は表示される) |
| Nitpick 1 | `mkdir` 失敗後の存在確認の TOCTOU で、先発が直前に終了したとき「ロックを作成できません」と出る | **見送り**。終了コード 1 は正しく、何も消さない。表示の紛らわしさだけ |
| Nitpick 2 | `--keep` の案内で、パスと「を」の間のスペースが移行前から変わった | **修正済み**。`kept_description` を `スタックを` / `スタックと <パス> を` に変え、`it-common.sh:348,352,360` を修正(`bash -n` OK) |
| Nitpick 3 | `owner` の内容を無加工で表示している | **見送り**。別ユーザーとの排他は MVP の対象外 |
| Nitpick 4 | SC2034 対策を `set -euo pipefail` の後ろに置けば `--help` が変わらない | **記録のみ**。shellcheck はホストに無く未実施。使える環境で実行するときに検討 |

文言の 1 行だけを修正したので、code-reviewer の再レビューは省略した(修正は表示文言のみ。`bash -n` と、Crawler・Indexer の `--keep` の出力で確認)。

## 2. test-reviewer の結果と対応

Critical なし。Important 6 件はいずれも「検証手順の穴」で、コードの欠陥ではない。Docker を使わない検証を追加して解消した(3 章)。Phase 5 の手順には 4 章のとおり追記する。

| 指摘 | 内容 | 対応 |
| --- | --- | --- |
| I1 | ポート使用中の検出が未検証 | 3-A で検証済み |
| I2 | Crawler・api の空でない `data/` の中止、api の `chmod 000` が未検証 | 3-B で検証済み |
| I3 | 「何も消さない」の証拠が弱い(スタックが元々無い) | 3-C(偽の `docker` の呼び出しログ)で検証済み。実スタックでの確認は Phase 5-2(ii)(iii)・5-5 |
| I4 | 全件実行の合格判定が終了コードだけ(skip を検出できない) | Phase 5 で件数と skip の判定を追加(4 章) |
| I5 | `--keep` と down 失敗の検証が偏っている | Phase 5 に Crawler の `--keep` と `data/` の保持確認を追加(4 章) |
| I6 | TERM・INT の送り方(`caffeinate` の PID、bash の trap 保留) | Phase 5 の手順を修正(4 章) |
| S1〜S4 | Docker なしの旧・新比較、ロック解除失敗の 11、競合、uv なし | 3-D〜3-G で実施済み |
| S5 | 作業記録の根拠(誰が確認したか、実コマンド) | 本記録で、確認者と結果を明記。0004 で「実装者の確認のみ」としていた 2 項目は、メインエージェントが再確認した(3-H) |

## 3. 追加の検証(メインエージェントが実行。いずれも `loreley-it` のスタックは作らない)

ツール: スクラッチパッドの偽の `docker`(v2。呼び出しを `FAKE_DOCKER_LOG` に記録。`stub-compose` モードは `compose up` を失敗させ、それ以外の `compose` は本物に渡さず成功を返す)。全文は 0004 の偽の `docker` に、次の追加を加えたもの。

```bash
[ -n "${FAKE_DOCKER_LOG:-}" ] && echo "docker $*" >> "$FAKE_DOCKER_LOG"   # 全呼び出しを記録
  stub-compose)
    if [ "${1:-}" = compose ] && ! has_arg version "$@"; then
      if has_arg up "$@"; then echo "fake: compose up を失敗させた" >&2; exit 1; fi
      exit 0
    fi ;;
```

### 3-A ポート占有(I1)
空いているポートを `python3 -m http.server` で占有し、`stub-compose` で実行。
- Crawler(9200・8000・8001)、Indexer(9200・8000)、api(9200・8000・8001・8080)の全 9 ポート: すべて終了コード 1、該当ポートの「使用中です」表示 1 件、lsof による相手の表示、`compose up` の呼び出し 0 回
- Indexer は 8001・8080 が使用中でも、ポートでは中止せず(`IT_PORTS` に含まれない)、`compose up` まで進み、stub の失敗で終了コード 10。`down -v --remove-orphans` が 1 回呼ばれた
- Indexer の新規追加分(ポート使用中の相手の表示)も動作を確認した

### 3-B 空でない `data/`(I2)
- Crawler・api の `data/canary.txt`: どちらも終了コード 1、canary は残った、`compose up/down` の呼び出し 0 回、ロックなし
- api の `data/` を `chmod 000`: 終了コード 1、「内容を確認できませんでした」、`data/` は残った(Crawler の chmod 000 は 0004 で確認済み)

### 3-C 呼び出しログ(I3)
`fail-ps-a`(3 本)、`fail-volume-ls`(Crawler・Indexer)、ロック保持中(3 本): すべて終了コード 1、`docker compose ... up|down` の呼び出し 0 回。ロック保持中は docker の呼び出し自体が 0 回(ロックは前提確認より前)。ロック保持中の実行後も、先発のロック(`pid=999999`)は残っていた。

### 3-D 旧スクリプト(`96a9b52`)と新スクリプトの比較(S1)
`git archive 96a9b52 scripts` の旧と現在の新を、スクラッチ内の別ツリーで、`/bin/bash`(3.2.57)・全部成功する偽の `docker`・引数と環境変数を記録する偽の `uv`・`TMPDIR` 分離で実行(3 本 × normal・`--keep`・down 失敗・uv の失敗(終了コード 3)・`-k foo -x`)。
- 終了コードは旧・新で一致。意図した差は、Crawler・Indexer の down 失敗時のみ(旧 0 → 新 11)。api は旧・新とも 11、uv 失敗は旧・新とも 3
- docker の呼び出し記録: api は差分なし。Crawler は URL 3 つ(`LORELEY_IT_{CRAWLER,INDEXER,OPENSEARCH}_URL`)の追加のみ。Indexer は URL 2 つの追加と、残骸確認(`docker ps -a`・`docker volume ls`)の追加のみ
- pytest の引数: api `-v -rP -k foo -x`、Indexer `-v -k foo -x`(旧・新で同一)。pytest 引数が空のときの `set -u` 展開(bash 3.2)も、normal の実行で問題なく通った
- `--keep`: Crawler は「スタックと <パス> を残しました」、Indexer は「スタックを残しました」(パスなし)。後始末コマンドの案内も正しい
- どのケースでも終了後にロックが残らなかった

### 3-E uv が無いとき(S4)
PATH から uv を外した(docker は全部成功の偽)。Crawler・api・Indexer は終了コード 1、「uv が見つかりません」。Indexer に `LORELEY_IT_PYTEST_CMD=true` を指定すると uv の確認を通り、終了コード 0。

### 3-F ロック取得の競合(S3)
Crawler と Indexer を同時に起動(`hang-info`)する試行を 10 回: 毎回、ちょうど 1 本が中止し 1 本がロックを保持した(10/10)。終了後に stray プロセス・ロックなし。

### 3-G ロック解除失敗の終了コード(S2。関数レベル)
`it-common.sh` を `source` し、`acquire_lock` の後に親ディレクトリを `chmod 555` にして解除を失敗させた。テストが成功(0)のとき終了コード 11 と手動解除の案内、テストが失敗(3)のとき元の 3 を返し、「11 で終了」は出なかった。

### 3-H 0004 で「実装者の確認のみ」としていた項目の再確認
- `LORELEY_IT_WAIT_TIMEOUT_SECS=abc`(3 本)・`=0`(Crawler): 終了コード 1、ロックなし
- Indexer の `LORELEY_IT_PYTEST_CMD="  "`: 終了コード 1、「空白だけです」、ロックなし
- 共通ファイルを削除したコピーで `--help`(3 本): 終了コード 1、「共通ファイルが見つからないか、読めません」、ロックなし

## 4. Phase 5 の手順への追記(0002 4 章 Phase 5 を、次のとおり補う)

- 判定: ログの最終行から件数を抽出して照合する(Crawler `14 passed`、Indexer `40 passed`、api `23 passed`)。`skipped`・`deselected`・`xfailed`・`warnings` を含まないこと(api は `-rP`)。ログのファイル名と最終行を作業記録に残す
- 5-1(Crawler の 11): 終了コード 11 の後に、`tests/integration/crawler/data` が存在する、コンテナが残っている、ロックが無い、を確認する
- `--keep` を Crawler でも実施する(`-k test_01_startup`): ロックが無い、スタックと `data/` が残る、表示された後始末コマンドでそのまま片付く、片付ける前の再実行は残骸確認で中止する
- 5-4(TERM): スクリプトの PID(ロックの `owner` の `pid=`)に送る(`caffeinate` の PID ではない)。待機ループ中(「スタックの起動を待っています」の後、コンテナができた時点)に送り、`compose up` の最中は送らない(bash の trap が子の終了まで保留されるため)。判定は、終了コード 143、`loreley-it` のコンテナ・ボリューム 0 件、ロックなし
- 5-5(同時実行): 2 本目の実行中に `docker events --filter label=com.docker.compose.project=loreley-it` を記録し、destroy・die・kill が出ないことも示す。1 本目のコンテナ ID・ボリュームの不変は従来どおり
- 静的な旧・新の比較(3-D)を、環境変数と pytest コマンドの同一性の証拠とする(`LORELEY_CRON_TIMEZONE=UTC` などは compose の既定値と同じで、export が落ちても成功実行では検出できないため)

## 5. 事故の記録(正直な報告)

3-A の初回実行で、私のループが zsh の単語分割の違いでポート番号を誤り(`9200 8000 8001` を 1 つの値として渡した)、**偽の `docker` の `stub-compose` を指定する前に、本物のスタックを起動する形で Crawler の IT が走った**。
- Crawler: `14 passed in 37.90s`、終了コード 0(`tests/integration/crawler/results/pytest-20261126-040531.log`)。新しい共通化スクリプトが、本物のスタックで Crawler を通した初めての記録になった。ただし、正式な Phase 5 の記録は取り直す
- 続く Indexer の実行中に `TaskStop` でシェルを止めたところ、スクリプトごと強制終了され(SIGKILL 相当)、`loreley-it` の 3 コンテナ・1 ボリュームとロックが残った
- 対応: ロックの保持者(PID 33631)が動いていないことと、残っているコンテナ・ボリュームがすべて `loreley-it` のものであることを確認してから、`docker compose -p loreley-it -f deploy/compose/compose.yaml -f tests/integration/indexer/compose.test.yaml down -v --remove-orphans` と `rm -rf` のロック解除で片付けた
- 影響: 他プロジェクトのコンテナ・ボリューム(`opensearch-opensearch-1`、`opensearch-data`、`opensearch_opensearch-data`)は変化なし。`data/` なし、ロックなし
- 再発防止: ポート検証を bash のスクリプトファイル(`ports.sh`)にし、ポートを占有できたことを確認してから実行し、`stub-compose` で `compose up` を本物に渡さない形にした。実スタックを起動する検証は Phase 5 だけに限る
- 副次的な確認: ロックが `kill -9` 相当で残り、次の実行が止まったことは設計どおり。手動解除の手順に従って片付けられた

## 6. 未実施・未検証

- shellcheck(ホストに無い)
- Docker のスタックを実際に起動する検証は Phase 5 で行う(`--keep`、down 失敗の 11、Indexer の残骸検出、TERM、同時実行の拒否、3 本の全件実行)
- 既知のリスク(0002): `mkdir` 成功から `lock_acquired=true` までのシグナルでロックが残る

## 次のアクション

1. Phase 5(Docker を使う検証・全件実行)を、4 章の追記を含めて実施する
2. Phase 6(README・結果文書)→ Phase 7(document-reviewer)→ Phase 8(task-reviewer)

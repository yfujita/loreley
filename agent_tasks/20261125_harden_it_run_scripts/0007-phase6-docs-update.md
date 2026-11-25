# 0007 Phase 6: README・結果文書の更新

日付: 2026-11-26 / 実施: `document-writer` / 変更範囲の確認: メインエージェント(`git status`・`git diff --numstat`)
基準: コミット `96a9b52`。コミットはしていない。

## 変更ファイル

- `tests/integration/{crawler,indexer,api}/README.md`(api 20 行、crawler 28 行、indexer 26 行の変更)
- `docs/v0.x/test-results/{crawler,indexer,admin-api}-integration.md`(末尾に章を追記のみ。削除行 0。追加 44・46・43 行)
  - 追記した章: crawler 9 章、indexer 10 章、admin-api 10 章(見出し「実行スクリプトの安全性の統一と排他ロック(再実行の記録。2026-11-26)」)。依頼文の章番号(「9 章まで」などの言い方)と実物の既存の章数がずれていたため、実物の最終章の次の番号にした
- 作業記録・`STATUS.md`、`scripts/`、`apps/`、`tests/` の Python・compose、`deploy/` は変更なし(`git status` で確認)

## README の更新要点

- 終了コード表: 終了コード 1 に「ロックを取れなかった」を追加。Crawler・Indexer に終了コード 11 の行を新設。api の 11 に「ロックの解除」を追加。テスト失敗時は pytest の終了コードを優先する旨
- URL の固定: Crawler(OPENSEARCH・INDEXER・CRAWLER)・Indexer(OPENSEARCH・INDEXER)を追記。pytest を直接実行するときだけ環境変数で変えられる旨。api は既存の記述が実装と一致していたため触っていない
- 事前確認で中止する条件: Crawler・api を実装に合わせて更新。Indexer は追加された条件(コンテナ・ボリュームの残り、ポート使用中の相手の表示、docker の失敗)を新規に記載
- 同時実行: 旧「同時に動かせない」の節を「結合テスト同士は同時に実行できない(排他ロック)」に置き換え。後発の中止、ロックの置き場所(`${TMPDIR:-/tmp}/loreley-it.lock`)、解除のタイミング(通常終了・INT・TERM・`--keep`)、`--help`・引数エラーでは作らないこと、SIGKILL・電源断で残った場合の手動解除手順(`ps -p` → `rm -rf`)、誤って実行中のロックを消したときの挙動(PID 不一致で警告のみ)、`TMPDIR` が異なる環境や pytest・compose の直接実行は排他されないこと
- ファイル構成の表の直後に、`scripts/lib/it-common.sh` が 3 本の共通処理であることを 1 行で追記

## 結果文書の追記要点

- 構成: 変更した資材(基準 `96a9b52` の作業ツリー、未コミット)、実施条件、全件実行の結果、その IT に関わる検証、静的検査と未実施
- 全件実行: Crawler `14 passed in 36.99s`(`pytest-20261126-041916.log`)、Indexer `40 passed in 17.19s`(`pytest-20261126-042111.log`)、api `23 passed in 423.90s`(`pytest-20261126-042255.log`)。いずれも終了コード 0、skip なし、残骸なし。Crawler には、0005 の事故で意図せず走った回(`14 passed in 37.90s`、`pytest-20261126-040531.log`)も別行で併記
- shellcheck は「未実施(ホストに無い)」と明記。偽の `docker` での確認と実スタックでの確認を区別して記載。api の実スタックで行っていない項目を明示
- 既存章の古い記述(crawler 7・8 章、admin-api 9 章の「未対応」など)は書き換えず、新章の冒頭で解消した旨を参照

## `document-writer` の判断・未対応(報告のとおり)

- Docker・compose・uv の版は 0003〜0006 に記録が無いので「今回は記録していない」と書いた
- 各 README の冒頭にある「確認状況」の注記(日付・件数)は据え置き(結果は結果文書に書く方針)。更新するかはユーザー判断
- 0000 の As-Is の食い違いは触っていない

## 次のアクション

- Phase 7: `document-reviewer`(スクリプトの実際の挙動と文書の一致、結果文書が作業記録 0004〜0006 と一致しているか、既存章が書き換わっていないか、未検証を「確認済み」と書いていないか)
- Phase 8: `task-reviewer`

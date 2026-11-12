# 0007 レビュー R1 と指摘対応

日付: 2026-11-12
レビュー: code-reviewer(読み取りのみ。コンテナ操作なし)/ 対応・実機確認: メインエージェント

## レビュー対象

`infra/opensearch/init-indices.sh`、`infra/opensearch/schema/{search-index,deletions,jobs}.json`、`deploy/compose/{compose.yaml,.env.example,README.md}`(比較基準 `c59fea7`)

## 判定: 修正後可(Critical なし、Important 1 件)

指摘なしの観点: ポート公開(127.0.0.1 のみ。`config` で確認。ホスト側ポートの変数化でもバインド先は固定。9600・9300 は非公開)、イメージ固定、init の冪等性・エラー処理(HEAD の 200/404 以外は失敗、作成競合は skip、curl の接続失敗とタイムアウト、`set -e` の落とし穴なし、一時ファイルの trap 削除、応答本文に秘密なし)、healthcheck と `depends_on`、マッピングと `records.py` の突き合わせ(deletions 30 項目が過不足なし)、`--wait` を使わない記述と 0006 の整合、読み取り専用 mount、要件にない機能の追加なし。

## 指摘と対応

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | opensearch に restart ポリシーがなく indexer だけ `unless-stopped`。デーモン・ホスト再起動や OOM のあと、indexer だけが起動して終了・再起動を繰り返す | **対応済み**: opensearch に `restart: unless-stopped` と理由のコメントを追加(init は `no` のまま)。`config` で確認 |
| Suggestion | init が、再インデックス後(-000002 へ切替え -000001 削除)に空の -000001 を毎回作り直す | **対応済み**: 検索インデックスはエイリアスの有無で判定し、無いときだけ「作成 → 付与」にした。実機で確認(下記) |
| Suggestion | `deploy/compose/.env` が gitignore されていない | **対応済み**: `.gitignore` に追加 |
| Suggestion | README の仮定義の記述が jobs だけ。jobs の型指定による制約も未記載 | **対応済み**: 節を「deletions と jobs」に拡張し、型制約(不正な文書は OpenSearch が拒否するので、Indexer の fail-closed 分岐は実機で再現できない)を追記 |
| Suggestion | url・path の `doc_values: false` は未決(設計書 U-8) | **見送り**: 設計書の JSON と一致させる。設計に関わるためユーザー判断事項。結果記録に「U-8 は未対応」と残す(フェーズ 6) |
| Nitpick | 「フェーズ 3 で確認後に追記」が残る。compose.yaml が未作成のスクリプトを参照。Linux の `vm.max_map_count` は Mac では未確認。マッピング変更時の手順 | **フェーズ 5・7 で対応**(スクリプトはフェーズ 5、README はフェーズ 7)。Linux は「未確認」と明記する |
| Nitpick | init のエラー表示の細部((a) acknowledged:false のとき `failed: HTTP 200`、(b) HEAD の失敗時は本文なし)、(c) SELinux の `:z` | **見送り**(任意。(c) は Linux 確認時に README へ) |

## 実機確認(init スクリプト変更後)

`-p loreley-it` で実施:
- 初回: `created: index loreley-documents-000001`、`created: alias`、deletions・jobs を作成して終了コード 0。opensearch・indexer とも healthy。
- 再インデックスの模擬: `loreley-documents-000002` を作成し、エイリアスを付け替え、`-000001` を削除してから `up -d`。init は `skip: alias already exists`、`skip: index already exists`(deletions・jobs)で完了し、`-000001` は作り直されなかった(残ったのは `-000002`、deletions、jobs)。
- `down -v` で後始末済み。

## 再レビュー

Important があったため、プランに従い同じレビュアーで再レビューした。**結果: 指摘なし(新たな Critical・Important なし)**。確認内容: restart の追加とコメントの整合、`.gitignore`、README の仮定義の節、init スクリプトの `set -eu` 下での `if exists ...` 分岐(HEAD が 200・404 以外や接続失敗は `exit 1` で、判定を誤って作成に進まない)、部分失敗からの再実行(作成後・付与前の失敗、再インデックス後)。見送りの 5 項目に異論なし。**R1 完了**。

## 未対応事項・次にやること

- フェーズ 4(結合テスト資材)へ。`uv` が使えることが前提(`brew install uv` は python@3.15 のソースビルド中)。

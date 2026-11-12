# タスク状態

## 基本情報

- 状態: done
- 現在工程: なし(追加指示「PDとSDの更新」も完了。ユーザー確認事項への回答を 0028 に反映済み)
- 最終更新: 2026-11-12
- 最新作業記録: 0028-user-answers-and-api-example-fix.md

## 追加指示(2026-11-12、完了後)

ユーザー指示: 「PDおよびSDから外れた実装があったと思う。PDとSDを更新して」。実装が設計書(PD・SD)から外れた箇所(0020 §6〜7 の設計書改訂候補。承認済み)を、PD・SD に反映する。docs は改訂ごとに新しい版のファイルを作る運用(PD は冒頭に改訂履歴)。`apps/indexer` のコード・テストは変更しない。

**コミット状況の訂正**: 実装はユーザーが 2026-11-12 11:06 に `d4daa1b Add indexer` でコミット済み(`apps/indexer`・`agent_tasks` の 0000〜0021 を含む)。以降の記述にある「未コミット」「HEAD は c065b9e」は古い。この追加指示のレビュー比較基準 SHA は `d4daa1b50ffe86a6aad713e0757ba4699a937ee3`。

プラン(0022)を planner が作成した(逸脱の棚卸し A〜E、版の方針(PD v0.19、arch・api・del・si v0.10、module v0.4)、K57〜K71 の割当、Phase 0〜7、レビュー計画)。

**ユーザー承認(2026-11-12。AskUserQuestion の回答)**: Q1=区分は「承認済みのみ確定」(明示承認分=0002 §3 の22項目・0014・0021 は「確定」にして根拠に承認日と記録番号を書く。Crawler・infra 依存の名称・形式は案のまま「実装で採用中」と注記。設計書の案どおりに実装しただけのもの(module の M-n など)は区分不変で実装済みの注記のみ)/ Q2=PD に入れる範囲は4件(原本サイズ超過で既存データを残す、要約の有効化後の既存文書と再試行の暫定方針(LLM 未実装に触れる)、要約の入力が先頭の一定文字数、TTL 誤設定のリスク(追加条件なし))/ Q3=arch・api・del・si を v0.10 に揃えて改版(si は参照更新と注記のみ)、module v0.4、PD v0.19、arch・api・del・si の末尾に「v0.9 からの変更点」の節。Q4〜Q6(新設定は名前・役割のみ設計書に・値は README を正とする/README・コード内の docs 参照 v0.9 は本タスクで直さない/arch 16章は既存行の訂正のみ)は推奨案で進める(異議なし)。

(履歴)Phase 3b・3c(0025): 再レビュー2名の結果、Phase 3a の Important は全て解消、Critical なし。残りは「確定/案」の書き分けのずれ(Important 4件=ソース削除の試行上限超過の 503 は K61 の本文に含めて確定/承認表記の規則を統一(0021 §1・§2 が名指ししたものは「0021 §n」、名指しされていないものは案+「0020 §6-2(0021 で全て承認)」)/arch 2.4 のアクセスログの内容は案/`reason_detail` の確定表記の位置)と参照・表記の不揃い。3b-2 は修正済み(0027 §1)。
Phase 3a 完了(0024): document-reviewer 4名(arch・api・del+si・module)の判定はいずれも「軽微な修正で可」(Critical なし)。主な指摘は、承認範囲を超えた「確定」の書き方(状態名 P25、`finished_at`、要約の生成前フラグ確認、起動順・停止順、BOM・私用領域、TTL 丸め、保持件数の整理)と、文書間の区分の不整合、起動前 503 の実態(外からは接続拒否に見える)との食い違い。**承認の個別記録がないものは「案(実装で採用中)」にとどめる**(Q1 の方針。共通の決定 D1〜D15 は 0024 §2)。今回「案(実装で採用中)」にとどめた項目は、ユーザーが後で確定に昇格できる(完了報告で一覧を提示する)。
進捗(Phase 1〜2。0023): arch v0.10(1356行)、api v0.10(892行)、module v0.4(555行)、loreley-deletions v0.10(291行)、search-index v0.10(373行)を新規作成(旧版は無変更)。各担当が報告した保留事項(P25 状態名は案のまま・要約の生成前フラグ確認は「実装で採用中」と注記・K なしの確定項目の整合 ほか)は 0023 に記録し、Phase 3b で修正する。次: Phase 3a(document-reviewer を文書ごとに並列)→ 3b(修正と再レビュー)→ 3c(文書間整合)→ Phase 4 PD v0.19 → document-reviewer → task-reviewer。

ユーザー回答(2026-11-12。0028): PD 8.2 の要約基準は現状どおり(C)、api の例 JSON の具体値は `"<値は未決>"` に戻した、他の確認事項は提示した方針どおり(案のまま・追加注記なし)。

進捗(0026・0027): task-reviewer は「修正後可」(Critical なし)で、指摘は対応済み(0027 §2)。 SD の最終確認は Critical・Important なし(軽微な修正を反映済み)。PD v0.19 を作成し、document-reviewer の指摘(Important 3件・Suggestion・Nitpick)のうち承認範囲内のものを反映。**ユーザー判断待ち**: PD 8.2 の要約基準と LLM 具体プロバイダ未実装の食い違い、8.2・5.2 の「TTL が正しく設定されている前提」の注記、K61 の確定の範囲(S-2)、0021 §1 の仮定義を案のままにしてよいか(0026 §3)。新しい docs 6ファイルは未コミット(`.obsidian/workspace.json` は含めない)。

## 現在の状況(実装完了時点)

要件(Indexer の実装・単体テスト・仕様確認)は完了。`apps/indexer` に設計書(module v0.3 の3層)どおりの Indexer を実装した(P1〜P6、作業記録 0003〜0021)。**未コミット**(HEAD は c065b9e のまま。ユーザーが「まだコミットしない」とした)。

最終検証(メイン、2026-11-12): pytest **2119 passed**(3回連続)、ruff check/format 通過、`uv lock --check` OK。**`docker build apps/indexer` 成功**、実コンテナで `/healthz` 200・HEALTHCHECK `healthy`・`docker stop` 0.86秒・終了コード0(偽の OpenSearch に対して)を確認(0020 §3)。タスクレビュー(task-reviewer)は「修正後可」で、指摘はすべて対応済み(0020 §1〜3)。

ユーザー承認(2026-11-11・12): Q1〜Q3(0001)、プラン §3 の22項目の案(0002。全て案どおり)、0014 の3件、**2026-11-12 に承認未取得だった事項(設計書から外れた判断・追加した設定・依存・運用)をすべて承認**(0021)。

注意: 検証は fake・ローカルスタブ・偽の OpenSearch に対するもので、**実 OpenSearch・実 Crawler・実 LLM に対する動作は未確認**(U-31 ほか。0020 §8)。

## 次のアクション

- なし(完了)。ユーザーの指示があれば次を行う:
  1. コミット(新版 docs 6ファイルと agent_tasks。`.obsidian/workspace.json` は含めない)
  2. Crawler との突き合わせ(U-34)、U-31 の実機確認、README・コード内の docs 参照(v0.9)の更新

## 未解決事項

- **U-31(実 OpenSearch での確認)**: 楽観ロック・`delete_by_query`・`search_after`・painless の max 比較・refresh・404 の本文の形 ほか(0020 §8)
- **Crawler との突き合わせ**: `document_id` の先頭 `/`、`content_hash` の小文字 hex、DELETE のボディ(`lock`)、孤立サロゲート、ID 長の上限、ロック文書・メンテナンスフラグの形式(fail-closed)、索引名・マッピング前提
- 既知の制限(README に記載): TTL・`ratio_threshold`・`min_delete_count` の誤設定リスク(ユーザー判断で追加条件なし)、判定時の `MalformedRecordError` が待ち行列の先頭を詰まらせる、要約の再開遅延と先頭30,000文字のみ要約・要約は LLM プロバイダ未実装のため有効化すると起動失敗、巨大 HTML の処理時間、同一 `crawl_id` の別 `source_id` 同時開始
- R6・R7・R8 の依存ルールは部分検査のみ
- docs への反映: PD v0.19・SD 新版(arch/api/del/si v0.10、module v0.4)で実施済み(0022〜0027)。持ち越し: README・コード内の docs 参照が v0.9 のまま、si 2.4 の `external_id` 正規化は未反映、U-34(Crawler との突き合わせ)
- 0000 の空欄(制約・前提条件/完了条件/成果物)への反映はユーザー任意(0001 の案で補完した)

## ユーザー判断待ち

- なし(コミットの要否のみ。指示があるまで行わない)

## 環境メモ

- レビュー比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体。`Dockerfile` は空ファイルからの変更)
- `uv` 未インストールのため、スクラッチパッドの venv に導入: `/private/tmp/claude-501/-Users-yfujita-fuji-private-github-loreley/c814dc96-a18d-4443-be98-443554fd0c80/scratchpad/uvenv/bin/uv`(0.13.7)。Python 3.12.11 は pyenv にあり(`UV_PYTHON=/Users/yfujita/.pyenv/versions/3.12.11/bin/python`)
- Docker デーモンは起動中(Docker 20.10.13)。確認用に作ったイメージ・コンテナ・偽 OpenSearch は片付け済み(取得したベースイメージ `python:3.12.16-slim-bookworm`・`python:3.12.11-slim-bookworm` は残っている)
- 無関係の `.obsidian/workspace.json` が作業ツリーに未コミットで残っている(コミットする際は含めない)

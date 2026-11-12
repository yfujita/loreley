# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(ユーザー承認済み。コミットはユーザーの指示待ち)
- 最終更新: 2026-11-12
- 最新作業記録: 0021-user-approval-and-completion.md

## 現在の状況

要件(Indexer の実装・単体テスト・仕様確認)は完了。`apps/indexer` に設計書(module v0.3 の3層)どおりの Indexer を実装した(P1〜P6、作業記録 0003〜0021)。**未コミット**(HEAD は c065b9e のまま。ユーザーが「まだコミットしない」とした)。

最終検証(メイン、2026-11-12): pytest **2119 passed**(3回連続)、ruff check/format 通過、`uv lock --check` OK。**`docker build apps/indexer` 成功**、実コンテナで `/healthz` 200・HEALTHCHECK `healthy`・`docker stop` 0.86秒・終了コード0(偽の OpenSearch に対して)を確認(0020 §3)。タスクレビュー(task-reviewer)は「修正後可」で、指摘はすべて対応済み(0020 §1〜3)。

ユーザー承認(2026-11-11・12): Q1〜Q3(0001)、プラン §3 の22項目の案(0002。全て案どおり)、0014 の3件、**2026-11-12 に承認未取得だった事項(設計書から外れた判断・追加した設定・依存・運用)をすべて承認**(0021)。

注意: 検証は fake・ローカルスタブ・偽の OpenSearch に対するもので、**実 OpenSearch・実 Crawler・実 LLM に対する動作は未確認**(U-31 ほか。0020 §8)。

## 次のアクション

- なし(完了)。ユーザーの指示があれば次を行う:
  1. コミット(`.obsidian/workspace.json` は含めない)
  2. 設計書・要件定義の改訂(別タスク。0020 §7 の改訂候補)
  3. Crawler との突き合わせ、U-31 の実機確認

## 未解決事項

- **U-31(実 OpenSearch での確認)**: 楽観ロック・`delete_by_query`・`search_after`・painless の max 比較・refresh・404 の本文の形 ほか(0020 §8)
- **Crawler との突き合わせ**: `document_id` の先頭 `/`、`content_hash` の小文字 hex、DELETE のボディ(`lock`)、孤立サロゲート、ID 長の上限、ロック文書・メンテナンスフラグの形式(fail-closed)、索引名・マッピング前提
- 既知の制限(README に記載): TTL・`ratio_threshold`・`min_delete_count` の誤設定リスク(ユーザー判断で追加条件なし)、判定時の `MalformedRecordError` が待ち行列の先頭を詰まらせる、要約の再開遅延と先頭30,000文字のみ要約・要約は LLM プロバイダ未実装のため有効化すると起動失敗、巨大 HTML の処理時間、同一 `crawl_id` の別 `source_id` 同時開始
- R6・R7・R8 の依存ルールは部分検査のみ
- docs への新設定・逸脱の反映は未実施(承認済み・別タスクで行う。0020 §7)
- 0000 の空欄(制約・前提条件/完了条件/成果物)への反映はユーザー任意(0001 の案で補完した)

## ユーザー判断待ち

- なし(コミットの要否のみ。ユーザーは「まだコミットしない」と回答済み。指示があるまで行わない)

## 環境メモ

- レビュー比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体。`Dockerfile` は空ファイルからの変更)
- `uv` 未インストールのため、スクラッチパッドの venv に導入: `/private/tmp/claude-501/-Users-yfujita-fuji-private-github-loreley/c814dc96-a18d-4443-be98-443554fd0c80/scratchpad/uvenv/bin/uv`(0.13.7)。Python 3.12.11 は pyenv にあり(`UV_PYTHON=/Users/yfujita/.pyenv/versions/3.12.11/bin/python`)
- Docker デーモンは起動中(Docker 20.10.13)。確認用に作ったイメージ・コンテナ・偽 OpenSearch は片付け済み(取得したベースイメージ `python:3.12.16-slim-bookworm`・`python:3.12.11-slim-bookworm` は残っている)
- 無関係の `.obsidian/workspace.json` が作業ツリーに未コミットで残っている(コミットする際は含めない)

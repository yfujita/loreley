# 0053 モジュール構成設計書 v0.3: summarization を documents 配下へ

## 経緯
v0.2 を確認したユーザーが「いい感じ」と返し、続けて「summarization は documents 配下がいいかも」と指示した(2026-11-11)。具体的な指示なので承認として扱う。軽微な構成変更のため、プランは作らず本記録で扱う。

## 実施した作業
- document-writer が v0.2 を元に `indexer-module-structure-v0.3.md` を新規作成した(版ごとに新ファイル。v0.1、v0.2 は変更しない)。
- メインは grep で確認した(M-1〜M-16、R1〜R9 が定義と参照で一致。旧構成の `summ` ノード、「2本」、R10 の取り残しなし。`summarization` の残りは `documents/summarization/` の表記と変更点の表のみ)。

メインが文書を直接直した箇所はない。

## 成果物
- docs/v0.x/system-design/indexer/indexer-module-structure-v0.3.md(494 行。v0.2 は 508 行)
- v0.1、v0.2、他の設計書、PD、0000 は変更していない。

## 変更点(v0.2 → v0.3)
- `summarization` を独立モジュールから `documents/summarization/` に移した(`documents/extraction/` と並ぶ)。アプリケーション機能の層は `crawl_runs` と `documents` の 2 つ。
- 機能どうしの層内の依存は `documents → crawl_runs`(受理条件の照会のみ)の 1 本だけになった(R3 の(b)を削除)。
- LLM クライアントは `infrastructure/llm` のまま。プロンプト組み立て、モデル選定、再走査、再試行の判断は `documents/summarization/` に残る。
- 起動時の再走査は、`documents` が公開する入口を `main.py` が呼ぶ。起動時の順序(整理は HTTP 受け付け開始前、再走査は並行可)は変えていない。
- 新しく決めた事項は M-9(`summarization` を `documents` の内部にする。案)。v0.2 の M-9〜M-11 は M-10〜M-12 に繰り下げ。M-ID は M-16 まで連続している。

## 判断
- 理由(案): 要約は登録済み文書への書き戻しで、起動の契機(登録の成功後。arch 4.3、7.2、G-12)を `documents` が持つ。実行タイミング(非同期、起動時の再走査)は内部に入れても変わらない。要約が大きくなれば独立に戻せる。
- 「内部ディレクトリを外から import しない規則」は v0.2 で削除済みのため、例外の理屈は書かず、再走査の入口を `documents` の公開する入口として明記した。

## 未対応事項
- **ユーザー判断待ち**: M-1〜M-15 はすべて案(特に M-9)。
- **既存の未決のまま**: `deletion/` の処理の開始契機(arch U-14)、ソース単位の排他の実現方法、ソース削除 2・3 のロック所有確認の担当(arch U-4、api API-U-14)、共通部品の置き場(M-16)。
- **Mermaid の描画は未確認**(Obsidian で要確認)。
- **v0.3 の document-reviewer によるレビューと task-reviewer は未実施**(構成の移動だけで、仕様は変えていないため省略。必要なら実施する)。
- **実装タスク `20261110_implement_indexer` の 0000** のディレクトリ構成案は、ユーザーの記載なので変更していない。v0.3 が確定したら差し替えるか判断が要る。
- v0.1 と v0.2 は旧版として残る(削除はしていない)。

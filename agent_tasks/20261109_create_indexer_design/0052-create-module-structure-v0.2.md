# 0052 モジュール構成設計書 v0.2 の作成(外部レビューの反映)

プランは 0051。ただし 0051 の次の記述を訂正する(既存の記録は書き換えない運用のため、ここで訂正する)。

## 0051 の訂正
- 0051 は「実装言語は設計書にも未決」としたが、**誤り**。実装言語は Python(arch 2.4、SD v0.8 §7.5 の「バックエンドは Python」)。未決なのは抽出ライブラリと文字コード判定の選定(U-10)。
- そのため外部レビューの Python 前提の指摘(パッケージ層 `loreley_indexer/`、`main.py`)は有効だった。v0.2 に案として取り入れた。
- 「`http` が Python 標準ライブラリと衝突する」という指摘は、パッケージ層があれば衝突しない(document-reviewer の指摘 I-1)。`api` への改名は、衝突の回避ではなく、API 層という役割が名前で分かるため。

## 実施した作業
1. 外部レビューを arch v0.9 と突き合わせて検証した(0051 の判定表)。
2. document-writer が `indexer-module-structure-v0.2.md` を作成した。
3. 言語の誤りに気づいた時点で、document-writer が Python 前提に修正した。
4. document-reviewer がレビューした(Critical 0、Important 5、Suggestion 6、Nitpick 5)。
5. document-writer が反映した(直さなかった指摘なし)。
6. メインが grep で確認した(M-1〜M-16、R1〜R9 が定義と参照で一致、旧名・旧 ID の取り残しなし、Mermaid ブロックは 7 つ)。

メインが文書を直接直した箇所はない。

## 成果物
- docs/v0.x/system-design/indexer/indexer-module-structure-v0.2.md(508 行)
  - 構成: 1 概要(モジュール表) / 2 構成図 / 3 ディレクトリ構成 / 4 モジュール詳細 / 5 シナリオ別の流れ(5.1〜5.6) / 6 依存ルール(R1〜R9) / 7 確認状況(M-1〜M-16) / v0.1 からの変更点(名前の対応表)
- v0.1 は変更していない。v0.9 以前の設計書、PD、0000 も変更していない。

## v0.2 の構成(すべて案。ユーザー未確定)
- 3 層: API 層(`api`)/ アプリケーション機能(`crawl_runs`、`documents`、`summarization`)/ infrastructure(`opensearch`、`llm`)。
- `crawl_runs` は arch 9章の Deletion Manager に当たる。内部を `lifecycle/`(状態管理)と `deletion/`(削除の判定・実行)に分ける。
- `extraction` は `documents` の内部、`storage` は `infrastructure/opensearch`、LLM クライアントは `infrastructure/llm`(プロンプト組み立て・再走査は `summarization`)。
- `src/loreley_indexer/`、`main.py`、`config.py` は Python 前提の案。

## 外部レビューのうち反映しなかった点
- 「`indexing → deletion` の依存がなくなる」: 受理条件の照会(arch K23)は残る。照会のみの案として維持した。
- 設計書内のファイル名(`service.py` など): モジュール内部のファイル名は書かない(実装時に決める)。

## 未対応事項
- **ユーザー判断待ち**: M-1〜M-15 はすべて案。特に、`crawl_runs` への改名と内部分割(M-3、M-13)、`api` の名前(M-2)、LLM クライアントの `infrastructure/llm` への移動(M-10)、パッケージ層・`main.py`・`config.py`(M-15)。
- **既存の未決のまま**: `deletion/` の処理の開始契機(arch U-14。イベント駆動なら `deletion/ → lifecycle/` の一方向の規則を見直す)、ソース単位の排他の実現方法、ソース削除 2・3 のロック所有確認の担当(arch U-4、api API-U-14)、共通部品(ログ、エラー型)の置き場(M-16)。
- **Mermaid の描画は未確認**(Obsidian で要確認)。
- **レビュー後の修正版の再レビューと task-reviewer は未実施**(追加の文書のため省略)。
- **実装タスク `20261110_implement_indexer` の 0000** にあるディレクトリ構成案は、ユーザーの記載なので変更していない。v0.2 が確定したら差し替えるか判断が要る。
- 508 行(目安の 450 行前後には届かず)。Mermaid のシーケンス図 5 本とモジュール詳細が大半。さらに減らすなら 4.1 の API 担当表などを削る。
- `v0.1` は旧構成として残る。使わないなら削除してよい(削除はしていない)。

# 0010 レビュー R2 と指摘対応

日付: 2026-11-12
レビュー: code-reviewer(スクリプト・設定・支援コード)/ test-reviewer(結合テスト)。どちらも読み取りのみ(コンテナ操作なし)
対応: スクリプトまわりはメインエージェント、テストは code-implementer(フェーズ 4 の担当)。再レビューは各レビュアーで行う。

## レビュー対象

`scripts/run-indexer-integration-test.sh`、`tests/integration/**`、`.gitignore`(追記分)(比較基準 `c59fea7`)

## 判定

- code-reviewer: **修正後可**(Critical なし、Important 2 件)
- test-reviewer: シナリオの過不足なし(範囲外の追加シナリオなし)。**Critical なし、Important 5 件(A〜E)**。全 36 テストの docstring に【何を確認するか】【前提と手順】【期待する結果とその根拠】【fake では確認できず実機で確認する点】があり、0000 の制約(コメントをリッチに)は満たしている。`force_last_seen_at` の使用は IT-13・IT-21 の前提作りに限られ、検証対象と循環していない。TTL は A=2 時間前、B=1 分前、ttl=600 で、最大 9 分の時計ずれに耐える。

## code-reviewer の指摘と対応

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | ホスト側ポートが固定のまま、compose は `.env` / 環境変数で変わりうる(テスト用スタックが別ポートで起動し、テストが「起動していません」と誤って中止) | **対応済み**: スクリプトで `OPENSEARCH_HOST_PORT`・`INDEXER_HOST_PORT` を 9200・8000 に export して固定(シェルの環境変数は `.env` より優先)。フェーズ 6 で効果を確認 |
| Important | 使用例の `-k IT-30` は 0 件一致(終了コード 5) | **対応済み**: `-k deletion` とファイル指定の例に差し替え、IT-nn がテスト名に含まれない旨を明記 |
| Suggestion | `requires-python` の範囲が広く uv の選ぶ Python が変わる | **対応済み**: `>=3.12,<3.14`(apps/indexer は `>=3.12,<3.13` だが、開発機の 3.13 で実績があるため `<3.14`) |
| Suggestion | `.gitignore` に `.ruff_cache/` | **対応済み** |
| Nitpick | 空白だけの `LORELEY_IT_PYTEST_CMD` で unbound variable | **対応済み**: `read` の直後で弾く(実機で終了コード 1 を確認) |
| Nitpick | cleanup の表示コマンドに `-f` が無い | **対応済み**: 「後始末します(…)」の表示に変更 |
| Suggestion | SIGTERM をスクリプトの PID だけに送ると、pytest の完了まで後始末が遅れる(bash の仕様)。後始末中の 2 回目の Ctrl-C で down が中断される | **見送り**(ローカル開発用途で許容。Ctrl-C は端末のプロセスグループ全体に届くので問題ない) |
| Suggestion | `compose down` の失敗が終了コードに反映されない | **見送り**(手動コマンドの提示があり、ローカルでは目視できる) |
| Nitpick | conftest.py の docstring が存在しない README を参照 | **フェーズ 7 で README を作るので対応**(作らなければ修正) |
| Nitpick | support.py の可読性(定数の配置、`fetch_*` の命名、`**kwargs`、素の `assert`) | **見送り**(任意) |

code-reviewer の確認で指摘なし: `set -euo pipefail`・PIPESTATUS・tee、trap の登録位置と二重実行、終了コードの設計、後始末の範囲(`-p loreley-it` 以外に触れない)、起動待ちの判定ロジック(init の ExitCode、unhealthy・restarting・exited。実機で再現できていない経路を精読で確認)、`/dev/tcp`、公開範囲(compose.test.yaml は `ports:` に触れず、両ポートとも `127.0.0.1`)、`document_id` の独立実装(README 6 章・Indexer の実装と一致)、HTTP タイムアウト。

## test-reviewer の指摘と対応方針(実装担当に依頼済み)

| 重要度 | 指摘 | 方針 |
| --- | --- | --- |
| Important A | IT-41 で、テスト側の `count()`(必ず `_refresh`)が、Indexer の「実行前 refresh」(K20、U-31 (5)(11))の欠落を隠す。docstring の「まだ検索可能になるまで待たない」は事実と違う | `refresh_interval=-1` を IT-41 の中だけで設定(try/finally で復元)し、登録直後の確認を GET ベースに変える。「検索可能でない状態を作れていること」もテスト内で事前確認する |
| Important B | IT-31 の複数ページ・複数バッチは、設定が効いていなくても通る(`Settings` は `extra="ignore"` で、環境変数名を誤ると既定値に黙って戻る) | 検索インデックスの `_stats/search` の `query_total` 差分で、ページ数(`>=4`)を実測する。バッチ数は直接観測できないので、推定であること・全 gone 文書が同一 `last_seen_at` を持つので tiebreak 欠落を検出できる性質を docstring に明記 |
| Important C | `expired_lease` が 1 分前で、時計のずれに弱い(Indexer の時計がホストより 60 秒以上遅れると偽の失敗) | 1 時間前に変更 |
| Important D | シナリオ ID でテストを選べない | **対応済み(スクリプトの使用例を修正)**。マーカー付与は要件外なので見送り。README(フェーズ 7)に ID とファイルの対応を書く |
| Important E | IT-42 は同一ソースの `deletion_result` が 1 件のケースのみ(「現行世代だけ消す」実装でも通る) | 同一ソースに複数の結果(C0 を終了通知まで済ませてから C1 を begin)がある場合も、すべて消えることを追加 |
| Suggestion N | IT-21 の docstring に事実誤り(「文字列比較なら +09:00 は Z より常に小さくなる」は誤り)。Indexer は正規化してから比較するので、文字列比較と `Instant` 比較は同値で、判別できるのは painless が実機で動くことと正規化の結果まで | docstring を実態に合わせ、限界を明記 |
| Suggestion R | IT-02 で Indexer との一致を確認するのは NFD+バックスラッシュの複合 1 件のみ(先頭 `/`・大文字小文字は独立実装でしか確認していない) | `/a.txt`・`a.txt`・`A.txt` の同一バッチ登録、NFD のみ・バックスラッシュのみを追加 |
| Suggestion S | IT-01 の deletions 読み取りの根拠が弱い(未知 ID の 404 だけ)。設計 9.5 K66 と、実装が `index_not_found` を 503 にするように読める点が噛み合わない可能性 | docstring を IT-20/22 との重複を認める形にし、コードを確認して事実を記載(設計との差の可能性があれば発見事項として報告) |
| Suggestion T | IT-40・IT-22 は Status API 経由の確認のみ(`deletion_result` レコードの直接確認なし) | `fetch_source` で `status`・`reason` を 1 回直接確認 |
| Suggestion Q | corrupt.pdf が「PDF ヘッダのないテキスト」のみ | **見送り**(任意。仕様どおりの別挙動になり得て、範囲が広がるため) |
| Nitpick | IT-12 の「クロール 1 は superseded」は未 assert、IT-14 の拒否経路が区別できない、IT-20 のマイクロ秒入力は切り捨て・四捨五入を区別しない、IT-20 はロック文書なしで開始通知を送る | assert 追加または記述削除、docstring に注記 |

## 最終報告に明記する事項(test-reviewer より)

- 「割合ルールで削除を見送る」安全機構(`skipped_by_ratio`)と、件数照合の不一致(`validation_failed`)は、結合テストで**未実施**である(0002 §11 論点 4 の推奨案どおりの除外で、ユーザー承認済み)。
- IT-31 のバッチ数は直接観測できず推定である(ページ数は `query_total` の差分で実測する予定)。

## 再レビュー

Important があったため、プランに従い同じレビュアー(code-reviewer・test-reviewer)で再レビューする。code-reviewer の分は軽微な修正のみなので、フェーズ 6 の実行確認(ポート固定の効果)とあわせて確認する。test-reviewer の分は、実装担当の修正後に再レビューを依頼する。

## 未対応事項・次にやること

- 実装担当の修正結果の確認(テストの再実行は、メインエージェントがフェーズ 6 でスクリプトにより行う)。
- test-reviewer に再レビューを依頼。
- `uv` が入ったら `uv lock` と、スクリプトを既定(uv 経由)で通すこと。`pytest` が `tests/integration/pyproject.toml` の設定を読むか(rootdir)もあわせて確認する。

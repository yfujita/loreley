# 0008 フェーズ4: 結合テスト資材

日付: 2026-11-12
実装: code-implementer / 確認・記録: メインエージェント

## 実施内容

0002 のフェーズ 4 に従い、`tests/integration/` に結合テスト資材を作成した。実装担当が、一時 venv(scratchpad の `it-venv`、Python 3.13.4、pytest 9.2.0、httpx 0.28.1)で実機スタック(`-p loreley-it`)に対して実行した。

## 変更ファイル(すべて新規。`.gitignore` のみ既存の更新)

`tests/integration/` 配下:
- `pyproject.toml`: 依存は `httpx>=0.27,<1`、`pytest>=8.3`(dev に `ruff`)。`[tool.uv] package = false`。`test_*.py` だけ E501 対象外(全角の日本語 docstring のため)
- `compose.test.yaml`: Indexer のテスト用上書き(`MAX_RAW_BYTES=65536`、`DELETION_BATCH_SIZE=2`、`SEARCH_AFTER_PAGE_SIZE=2`、`DELETION_POLL_INTERVAL_SECONDS=1`。環境変数名は `config.py` で確認し、`docker inspect` で反映を確認)
- `support.py`(プランからの小さな逸脱): Crawler 役クライアント(`CrawlerClient`・`Crawl`)、`OpenSearchProbe`、`document_id` の独立実装、時刻ヘルパ、`wait_for_terminal`。テストから import するため conftest と分けた
- `conftest.py`: フィクスチャと疎通確認(スタックが無いと `pytest.exit` で起動手順を表示)
- `samples/`: `sample.txt`・`sample.md`・`sample.html`・`sample.pdf`・`corrupt.pdf`・`README.md`(期待結果と PDF 生成方法)
- `test_01_startup.py`(IT-01)、`test_02_document_id.py`(IT-02)、`test_10_registration.py`(IT-10〜15)、`test_20_crawl_lifecycle.py`(IT-20〜22)、`test_30_deletion.py`(IT-30・31)、`test_40_source_deletion.py`(IT-40〜42)
- 既存: `.gitignore` に `tests/integration/.venv/`、`results/`、`.pytest_cache/`、`__pycache__/` を追加

## 判断・設計上の理由

- TTL は決定的: クロール A は 2 時間前開始・ttl 1 日、クロール B は 1 分前開始・ttl 600。待つのは削除ワーカーの走査(上限 30 秒のポーリング)だけ。
- `denominator` の期待値は設計書 9.3「削除前の同ソースの索引件数(TTL 期限内の文書も含む)」で決めた(IT-30 は 7、IT-31 は 8)。実機値と一致した。T=0 のクロール A でも `denominator` は 5 と記録されていたが、設計書は T=0 時の記録を明示していないので assert していない。
- IT-31 は `7/8 > 0.5` になるため `min_delete_count=100`(最小件数ルール)で削除させた。分割実行の確認が目的で、割合ルールの確認ではない(docstring に明記)。
- max 比較(`last_seen_at` が古い値に戻らない)の前提作りでは、通常の API の流れで受理中のクロールより新しい `last_seen_at` を作れないため、`OpenSearchProbe.force_last_seen_at` で文書を直接書き換える。IT-13・IT-21 だけで使い、docstring に明記。
- IT-15 はバッチ登録と `last-seen` の両方を、別 owner・別 job_id・期限切れ・ロック文書なしの 4 パターンで確認。IT-14 は実サイズ超過に加え「申告 size だけ超過」も確認。
- DELETE の JSON ボディは `httpx.Client.request("DELETE", ..., json=...)` で IT-41・IT-42 の実通信で確認。

## 実行結果(実装担当が実施、メインエージェントは未再実行)

- クリーンな状態(`down -v` 後に `up -d --build`)で **36 passed in 38.32s**。同じスタックへの再実行も 2 回連続で 36 passed。終了時は `down -v --remove-orphans` で片付け済み(`loreley-it` の残りなし。メインエージェントも `docker ps -a` で確認)。
- `ruff check` All checks passed、`pytest --collect-only` 36 collected。スタック停止時は疎通確認が起動手順を出して終了コード 2 で中止。
- メインエージェントの確認: ファイル構成と、IT-01・02・10〜15・20〜22・30・31・40〜42 の全 ID がテストに含まれることを確認。**最終的な実行はフェーズ 6 でメインエージェントがスクリプトで行う**(2 回連続成功を確認する)。
- 実機値(IT-30): A は `deleted`(deleted_count 0)、B は `enumerated_count=5`・`n_seen=4`・`e_missing=1`・`target_count=3`・`denominator=7`・`deleted_count=3`。IT-31: `target_count=7`・`denominator=8`・`deleted_count=7`。

## 発見事項

- Indexer の不具合: なし。設計との食い違い: なし。テストの誤り: なし(実機に合わせて期待値を変えた箇所なし)。Indexer ログに WARNING/ERROR なし。ホストと Docker VM の時計のずれは数秒以下。
- 留意: 全 36 件が初回で通ったため、テストが何も確認していない(偽陽性)リスクを R2 の `test-reviewer` で重点的に確認する(期待値の根拠、assert のメッセージ、OpenSearch の直接確認)。

## U-31 との対応(実機で確認できたもの)

(6) painless Update → IT-21・IT-12 / (7) 日時の `Instant` パース・date 型整合 → IT-10・IT-21・IT-20 / (9) 404 の応答形 → IT-21・IT-01・IT-22 / (5)(11) `delete_by_query`・refresh・`_count` → IT-41 / (12) `search_after` と `document_id` ソート → IT-31(複数ページになったことは設定値 2 と件数 7 から導く。API やログでは直接観測できない)/ 副次 `if_seq_no` → IT-12・13・30・31。
未確認(スコープ外): (1)(2)(3)(4)(8)(10)(13)。

## 未対応事項・次にやること

- `uv.lock` は未生成。uv が入ったら `tests/integration` で `uv lock` を実行する。uv は `brew install uv`(python@3.15 のソースビルド中)で、まだ入っていない。
- フェーズ 5: `scripts/run-indexer-integration-test.sh`(`conftest.py` の `STACK_HINT` がスクリプト名を参照)。`up -d --build` + 自前ポーリング、`--wait` は使わない。
- フェーズ 7 の README に「結合テストは専用の `loreley-it` で実行する(テストはデータを削除しない)」を明記する。
- R2 の観点: `force_last_seen_at` は前提作りに限定、複数ページの削除は間接的な確認、IT-30 の A の `denominator` は未 assert。

# 0006 フェーズ 3・4: テスト資材とテスト本体

日付: 2026-11-16
実装: code-implementer / 検証: メインエージェント(クリーンなスタックで再実行)

## 実施した作業の概要

- フェーズ 3: `tests/integration/crawler/` の pyproject.toml・`uv.lock`・samples・support.py・conftest.py、`.gitignore` に `tests/integration/*/data/` を追加。
- フェーズ 4: シナリオ CIT-01・10・20・21・22・30・40・50 を実装し、`loreley-it` スタックに対して実行・修正した。

## 変更したファイル

- `.gitignore`(`tests/integration/*/data/` を追加)
- `tests/integration/crawler/`: `pyproject.toml`、`uv.lock`、`support.py`、`conftest.py`、`test_01_startup.py`、`test_10_source_registration.py`、`test_20_crawl.py`、`test_30_ttl_deletion.py`、`test_40_source_deletion.py`、`test_50_maintenance.py`、`samples/`(`sample.{txt,md,html,pdf}`、`nested/sample-nested.txt`、`ignored.csv`、`.hidden.txt`、`README.md`)
- `apps/crawler`・`apps/indexer` は変更していない(`git status` で確認)。Crawler の不具合・設計との食い違いは見つからなかった。

## 実行結果

| 実行 | 結果 |
| --- | --- |
| 実装担当(同一スタックで 2 回) | 13 passed(47.49s / 41.61s)。初回に 1 件失敗(テスト側が `fetch_document()` の戻り値から `["_source"]` を引いた誤り)。テストを修正 |
| **メイン(クリーンなスタック、起動 → healthy 待ち → pytest)** | **13 passed(53.48s)、終了コード 0** |

メインの再実行後、`down -v --remove-orphans` と `data/` 削除で片付け済み(`ps -a` は空)。

### テスト一覧(13 件)

- CIT-01(3): crawler healthy、4 索引と alias、`loreley-sources` が strict・`loreley-jobs` が `dynamic:false` で Crawler が使う項目を定義
- CIT-10(3): 登録 201 と再送の扱い、未知の `connector_config` 項目の拒否、未登録ソースへのクロール起動は 404
- CIT-20/21/22(4): 5 文書の索引と件数照合(`enumerated_count == n_seen + e_missing`)、サイズ超過の記録と件数照合、(追加)サイズ超過でなくなった記録の整理、ロックの存在と解放
- CIT-30(1): TTL 削除(`last_seen_at` を過去に書き換え、`T=2`・`D=6`・`deleted=2`、他ソースは残る)
- CIT-40(1): ソース削除(対象のみ消え、他ソースは残る)
- CIT-50(1): メンテナンスフラグ時の 409 と解除後の 202

## 実機で分かったこと

- マウントの可視性の遅れは観測されなかった(ホストで書いた直後の `docker exec ls` で 10 回すべて即時に見えた。削除も即時)。`SourceDirectory` に有限ポーリングは足していない。
- ロック観測の窓は十分(リース付きで約 3.3 秒、0.2 秒間隔で約 16 回観測可能)。クロール 1 回は 3〜5 秒。
- メンテナンスフラグの形式はプランの仮定どおり(`maintenance` 文書の `enabled` が `False` でない限り「立っている」)。
- Crawler・Indexer のログに警告・エラーなし。ジョブ記録に `warnings` なし。

## プランとの差異

1. **未知の `connector_config` 項目は 400 `config_invalid`**(0002 の CIT-10 は `invalid_request` と書いた)。api 設計書 v0.4 の 3.3 とコードがどちらも `config_invalid` で、プランの記述の誤り。テストは設計に従った(結果記録に訂正を載せる)。
2. **テストを 1 件追加**: `test_oversize_record_is_purged_when_the_file_is_no_longer_oversize`(arch 6.4)。CIT-20 の「クロール終了後の整理」は記録がないと空振りになるため、既存シナリオの確認を実効的にする目的。新機能ではない。**R2 で是非を確認する**。
3. `conftest.py` に、前回の実行が残したメンテナンスフラグがあれば `pytest.exit` する確認を追加(残ると全クロールが 409 になるため)。

## 未対応事項・不確実点

- ロック観測は窓(約 3.3 秒)に依存。極端に速い環境では観測できず失敗するが、メッセージで原因が分かる。
- TTL の前提作りは Indexer 内部の項目名 `last_seen_at` に依存(Indexer の IT と同じ前例)。
- 実時刻の比較(リースが未来、`last_seen_at` が 1 時間以内)はホストと VM の時計に依存(許容幅は広い)。
- クリーンな状態からの一括スクリプトでの 2 回連続実行は、フェーズ 5・6 で行う。

## 次にやること

1. フェーズ 5: `scripts/run-crawler-integration-test.sh`
2. R2(`code-reviewer` + `test-reviewer`)。観点に追加テストの是非とロック観測の窓を含める
3. フェーズ 6 の結果記録に「`config_invalid`(0002 の `invalid_request` の訂正)」「マウントの遅れなし」を載せる

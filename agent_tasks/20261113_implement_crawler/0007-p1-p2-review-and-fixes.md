# 0007 P1+P2 のレビューと修正

日付: 2026-11-14 / 実施: code-reviewer・test-reviewer(2回ずつ)、code-implementer(修正)/ 記録・再検証: メインエージェント
レビュー比較基準: HEAD `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は新規・未コミット)

## 1. 1回目のレビュー結果

どちらも「軽微な修正で可」(Critical なし)。

### code-reviewer(Important 1、Suggestion 6、Nitpick 群)

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important | 全件走査・`list_records` が、部分シャード失敗・`timed_out` の検索結果を完全な結果として返す(ソース削除の順3で取りこぼし、孤児記録が残る恐れ) | `timed_out is True` または `_shards.failed>0` で `StoreUnavailableError("search_incomplete")`(`refresh_index` と共通ヘルパ)。検索に `allow_partial_search_results=false`、`create_pit` に `allow_partial_pit_creation=false` を渡す。PIT 作成応答の `_shards.failed` も検査し、PIT を漏らさず閉じてから送出 |
| Suggestion | `scan` の `sort` 一意性を呼び出し側に委ねており、破れると黙って取りこぼす | ページ内で隣接する hit の `sort` が等しければ `StoreUnexpectedResponseError("non_unique_sort")`(2回目の再レビューで、ページ境界をまたぐ比較は `search_after` が排他のため発火しない死んだコードと判明し削除。§3-1 の限界を参照) |
| Suggestion | PIT 期限切れが「Crawler の不具合」に分類される | `search_context_missing_exception`(本体または `root_cause`)を `StoreUnavailableError("pit_expired")` に分類 |
| Suggestion | `TransportError` 以外(`SerializationError` など)が分類を素通り | `OpenSearchException` まで捕捉し `StoreUnexpectedResponseError("serialization_error" / "opensearch_error")`。`_PitSession.close` も `OpenSearchException` で捕捉し元の例外を覆わない |
| Suggestion | リトライ後の `AlreadyExists` / `Conflict` の曖昧さ | `repository.py` の docstring に明記(§3-3 を P4 に周知) |
| Suggestion | `indexer_client` が応答の件数・対応を検証しない | `parse_last_seen` / `parse_batch` が件数・並び・重複を含め要請と完全一致を要求。不一致は `IndexerRejected(status, "malformed_response")` |
| Suggestion | `IndexerRejected.error_code` に任意文字列が入る | `[a-z0-9_]{1,64}` に `fullmatch` した場合のみ採用、外れれば None |
| Nitpick | `scan_page_size` 上限検証、`StoredRecord` 組み立ての重複(`client_calls.to_record` に集約)、`username`/`password` の片方だけの拒否、バルク削除の項目単位 400 系の docstring、`Timeout(read)` の意味の docstring、開始・終了通知の 200/202 以外の 2xx を `malformed_response` に(`expected_status`) | 対応済み |
| Nitpick | `display_text` が Zl/Zp/Cf(bidi 制御)を escape しない | **意図的に未対応**。docstring に「Cc のみ escape。Zl/Zp・Cf は対象外」と明記。再レビューで承認 |

code-reviewer が良い点として確認: 削除に関わる判断が一貫して安全側(想定外の応答は例外、`malformed_response` は非リトライ、refresh の不完全も全体異常)、例外とログに本文を載せない配慮。設計書にない2区分(`StoreUnexpectedResponseError`、`IndexerRejected("malformed_response")`)は「妥当で安全側」。

### test-reviewer(Important 5、Suggestion 6、Nitpick 7)

| 重要度 | 指摘 | 対応 |
| --- | --- | --- |
| Important I-1 | `FakeIndexerClient` が実クライアントの入力検証をしない(P6 の型 strict・終了通知固定・ポーリング区分の検証を誤って通す) | fake が `payloads.*_payload` の検証を共有。Status は未知=404 `crawl_not_found`、終了通知前=`running`、後=`deleted`/`failed`。開始・終了の再送の内容違いは409。終了通知のダイジェストを `apps/indexer` の `digest()` と突き合わせて一致を確認 |
| Important I-2 | `InMemoryRepository` が記録なしの版条件つき書き込みで `NotFound`(実 OpenSearch 3.9.0 は `Conflict`) | 既定を `Conflict` に。契約テストを `== Conflict()` に厳格化。`NotFound` は `behavior.inject` で注入 |
| Important I-3 | PIT スナップショット隔離が検証されていない | emulator に `refresh()`、契約テスト追加。emulator の PIT をコピーから参照にする変異が失敗として検出される |
| Important I-4 | `search_after` を外すとテストが無限ループ・2GB 超のメモリでハング | emulator に検索回数上限の保護、契約テストを `islice` で有界化。変異で 1.7 秒・13 failed(ハングなし) |
| Important I-5 | `indexer_client` の厳密型(`enumerated_count`・`size`)と failed/cancelled の件数送信が未検証 | テスト追加(`encode_json` の NaN/Inf 拒否を含む)。関連変異4件が検出される |
| Suggestion S-1〜S-6 | 依存許可表の全辺固定、`limit` 境界、タイムアウトテストの決定性(`Reply.wait_for`)、fake の配列・bool/int の忠実度(非対応を docstring に明記して許容)、PIT 期限切れの分類固定、契約テストの追加 | 対応済み(S-4 は文書化のみ) |
| Nitpick N-1〜N-7 | 型比較・`pytest.raises` の厳格化、`support.py` への移動、`Barrier`/`join` のタイムアウト、`connectors.web` の暫定ルールのコメント | 対応済み |

## 2. 2回目のレビュー(再レビュー)結果

両者とも「軽微な修正で可」。前回の Important はすべて解消。code-reviewer の残りは Suggestion A(死んだコード)・B のみ、test-reviewer の残りは S-6'・S-7(テストの検出力)と N-8・N-9。

- 修正後の変異確認(test-reviewer、約50件): すべて検出。生き残りは同値変異のみ。
- 新規テストの質は良好(`test_scan_safety.py` は部分失敗・`non_unique_sort`・`serialization_error`・PIT クローズ失敗を網羅。`indexer_client` の応答照合・契約外 2xx・`error_code` 境界も)。
- 新たに壊れやすくなった点なし(実時間を使うのは `Timer(0.5)` と 0.1/3 秒のタイムアウトのみ。順序は決定的)。

## 3. 3回目の小修正(再レビューの残り)

| 指摘 | 対応 |
| --- | --- |
| code Suggestion A | `scan.py` の `_ensure_sort_values_are_unique` から前ページ末尾との比較(`previous_last`)を削除、docstring を「ページ内の隣接」に。モジュール docstring にページ境界で同値が取り残される限界と、呼び出し側が `sort` を一意な `document_id` で終えるべきことを明記。対応するテストは発火するケース(2ページ目の中で等値)に差し替え |
| test S-6' | 複数キーソートのテストのデータを、キー優先順位が逆なら結果が変わる形に変更。2つの変異(in_memory と emulator の優先順位の逆転)が検出される |
| test S-7 | `hit["sort"][:sort_width]` を全体比較に変える変異を検出するテストを追加(検出を確認) |
| N-8・N-9 | `local_http_server.py` の未使用 `Reply.delay_seconds` を削除、`create` 引数に型注釈 |
| 後始末 | 実装担当が作った scratchpad の使い捨て物(`live_*.py`・`mutate.py`・`indexer.log`)を削除。実装担当の変異確認の残り(`rm -i ... payloads.py.bak` の入力待ちプロセス、13時間)はメインが終了(ファイルは存在せず無害) |

再検証(メイン): pytest 914 passed、ruff check・format --check・uv lock --check 成功、`git status` は `apps/crawler/` のみ。実装担当は3回連続で成功を確認。

## 4. 後続フェーズへの申し送り(重要)

1. **sort の一意性は呼び出し側の責任**(P4 `jobs/records`、P6 `crawl`、P7 `source_delete`): `scan` の `sort` は必ず一意な `document_id` で終えること。ページ境界をまたぐ同値は検出できず取りこぼす。呼び出し側のテストで「`sort` が `document_id` で終わる」ことを担保する。
2. **`pit_expired` の扱い**(P4・P6・P7): `StoreUnavailableError("pit_expired")` は操作単位のリトライでは直らない(generator が終了している)。**`with scan(...)` ブロック全体をリトライの単位**にする。
3. **リトライ後の `AlreadyExists` / `Conflict`**(P4 のロック取得・ハートビート・ジョブ記録更新): タイムアウト・接続断の後にリトライして返る `AlreadyExists` / `Conflict` は、実は初回が成功していた可能性がある。読み直して `owner` / `job_id` を確認し、自分の書き込みなら成功扱いにする。
4. **記録なしの版条件つき書き込みは `Conflict`**(実 OpenSearch 3.9.0 で確認、fake も同じ)。`NotFound` は版条件なしの取得・走査の結果区分。
5. **`StoreUnexpectedResponseError` の扱い**(P4・P5): Crawler の不具合として最後の手段 `failed(internal_error)` に落とす(リトライしない)。理由・種別名(`non_unique_sort`・`serialization_error`・`opensearch_error`・`http_NNN`)には本文を含まない。
6. 全体異常 `StoreUnavailableError` の理由: `search_incomplete`・`pit_expired`・`refresh_incomplete` ほか。リトライを尽くして `failed(store_unavailable)`。
7. `IndexerRejected("malformed_response")`: 契約外の 2xx、応答の件数・対応の不一致、200/202 以外の 2xx。リトライせずジョブを `failed` にする(P6)。
8. 設計書(architecture 9章)にない区分を追加した(次の設計改版の依頼リストに載せる): `StoreUnexpectedResponseError`、`IndexerRejected("malformed_response")`、上記の理由・種別名。
9. R7 の残りの検査(sources だけが `loreley-sources`、jobs だけが `loreley-jobs` を書く、読んだ版を条件にする、main が作る Repository が3つだけ)は P4・P5・P8 で追加する。

## 5. 実機確認が必要な項目(持ち越し。CA-U-18 など)

- `allow_partial_search_results=false` と `allow_partial_pit_creation=false` を OpenSearch 3.9 のサーバー側で PIT 検索と併用できるか(opensearch-py 3.2 の `query_params` に定義があり、渡し方はダミー transport で確認済み。サーバー側の実機確認は未)
- PIT 期限切れの実機の応答形(404 で `root_cause` に `search_context_missing_exception`。fake の再現であり実機では未確認の部分あり)
- `create` と `if_seq_no` の並行時の原子性、opensearch-py のスレッド安全性(CM-U-1)、実 Indexer での `document_id` 照合(CM-U-3)
- 補足(P2 の実機の使い捨て確認、0006 §5): OpenSearch 3.9.0 は存在しない索引への書き込みで索引を自動作成する。`action.auto_create_index` の無効化は infra 側の判断事項(別タスクに記録)

## 6. 補足

- 実装担当(`code-implementer`)の最終報告は `SubagentHandback` の制限で2回メインに届かず、再レビュー結果とディスク上のコードで解消を確認した。最後の小修正の報告は届いている。
- test-reviewer の再レビュー結果は、出力ファイルから最後の発言だけを取り出して確認した。

## 7. 次のアクション

- P3(`connectors`・`documents`)を `code-implementer` に依頼する。P3 完了後に code + test レビュー(0002 §6)。

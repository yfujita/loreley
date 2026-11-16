# 0021 最終整理(仮値一覧・採用案一覧・決めた内容・持ち越し・完了条件の検証結果)

日付: 2026-11-14 / 作成: メインエージェント / 作成時点の記録(案が変わっても更新しない)
対象: タスク `20261113_implement_crawler`(`apps/crawler`。Crawler の実装と単体テスト)。`apps/crawler/` は未コミット(コミットはユーザー指示があるときのみ)

## 1. 完了条件1〜10の検証結果(0001「完了条件」。プラン 0002 §7・承認済み)

最終検証(メインが再実行): `cd apps/crawler`: `uv run pytest -q` → **3249 passed, 3 skipped**、`uv run ruff check` → All checks passed、`uv run ruff format --check` → 277 files already formatted、`uv lock --check` → Resolved 39 packages。Linux(Docker)では非 root で **3255 passed・skip 0**(macOS の skip 3件は Linux で通る)。`docker build` 成功。

| # | 完了条件 | 結果 | 根拠 |
| --- | --- | --- | --- |
| 1 | `apps/crawler` が module-structure v0.4 の構成で存在し、依存ルール R1〜R6・R10 に反しない(`tests/architecture` の import 検査) | ○ | `tests/architecture/`(許可表・全辺固定・R7 の書き込み範囲・`main` が作る Repository は3つ・`jobs` 直下が `crawl`/`source_delete` を import しない・`main` を import するモジュールがない)。P1(0005)で作成、P5・P8 で最終確認(0011・0017・0018) |
| 2 | pytest・ruff・format がすべて成功し、結果を作業記録に貼る | ○ | 上記。各フェーズの作業記録(0005〜0020)に再実行結果を貼った |
| 3 | Admin API の6エンドポイントが crawler-api v0.3 の契約どおり応答(TestClient) | ○ | `tests/api/`(0017)。400(必須・型・未知項目・読み取り専用・形式不正 `reason`)・404・409(`source_deleting`・`maintenance_enabled`・`lock_held`)・503・500・共通エラー形式・結果型の全バリアントの写像・400 の本文に入力値が出ないこと・`/healthz`。メンテナンス中の設定更新・取り消し・ロック解放がフラグの影響を受けないこと(CAPI-P-17) |
| 4 | FS Connector: FS 設計書10章 #1〜23 と interface 10章の契約テスト(一時ディレクトリ・偽 `FsOps`。権限は root で skip、Linux 専用は macOS で skip) | ○ | `tests/connectors/`(0008・0009)。macOS の skip 3件(非 UTF-8 名・大文字小文字・NFC/NFD の併存)は `create_names_or_skip`(実際に作れるかで判定)。**Linux(Docker)で非 root・skip 0 を確認**。`LORELEY_REQUIRE_LINUX_NAMES=1` で skip を失敗にできる |
| 5 | architecture 12章のうち単体で可能なもの(fake の Repository・Indexer・固定時計・偽 Connector・偽 `FsOps`) | ○ | `tests/jobs/`・`tests/crawl/`・`tests/source_delete/`・`tests/scheduler/`・`tests/main/`(0011〜0019)。#13・#14・#15・#16・#18・#25〜#29・#32・#33・#35 ほか。`DELETE` のボディ(#17)はローカル `http.server` の契約テスト(0006) |
| 6 | `document_id` のテストベクタ(interface 5.2)を `tests/` のデータファイルに | ○ | `tests/documents/document_id_vectors.json`(全8行・10入力。Indexer の `compute_document_id` と一致を確認)(0008) |
| 7 | メモリ上 Repository が opensearch 実装と同じ契約(全件走査・ID のバルク削除(部分失敗を注入可能)・条件指定削除) | ○ | `tests/infrastructure/opensearch/test_repository_contract.py`(`InMemoryRepository` と実クライアント+fake transport の両方に同じ契約テスト)。条件指定削除は置かず、全件走査+バルク削除に統一(0006) |
| 8 | ログに本文・秘密・`connector_config` を出さない(テストで確認) | ○ | センチネル検査: `tests/crawl/test_logging.py`(14経路)・`tests/source_delete/`・`tests/scheduler/`・`tests/api/test_logging.py`・`tests/main/test_end_to_end.py`(`main()` 経由。マスキングの配線を含む)。例外は `from None`、固定文の理由名、`repr=False` |
| 9 | `docker build apps/crawler` が成功し起動を確認する | ○(範囲を限定) | `docker build` 成功。必須設定なし・Indexer 上限超過・索引名の同一・到達不能な OpenSearch のいずれも HTTP を開く前に終了コード1(fail-fast)、非 root(uid 10001)、`import` 確認。**PID 1 の `docker stop` は偽 OpenSearch で終了コード0・0.8秒**(code-reviewer が実機確認)。**実 OpenSearch・実 Indexer での `healthy` 化は Integration Test(スコープ外)に持ち越し**(0003 の合意どおり。`/healthz` の応答は TestClient と実 uvicorn+fake バックエンドで確認) |
| 10 | 作業記録に仮値一覧・採用案一覧・決めた内容・持ち越し一覧 | ○ | 本記録 §2〜§6 |

## 2. 採用した案の一覧(0001 Q3: 設計書の案どおり実装。**設計の承認ではない**)

decisions v0.3 の4章の10件+CM-U-4+CA-U-3。局所化した場所を併記(案が変わったときの差し替え箇所)。

| # | 案(ID) | 実装の局所化箇所 |
| --- | --- | --- |
| 1 | `source_id` の文字種: 半角英数字で始まり、半角英数字・`.`・`_`・`-` のみ(CAPI-P-15) | `sources/validation.py` の `SOURCE_ID_PATTERN`・`SOURCE_ID_MAX_LENGTH` の1か所(`api` は `check_source_id` を呼ぶだけ) |
| 2 | glob 構文と `include_patterns` は「既定拡張子への追加」(CFS-U-1) | `connectors/filesystem/patterns.py`(多項式時間の照合)・`config.py`・`settings.py` |
| 3 | `external_id` 衝突はジョブ `failed`(CA-P-24) | `documents/enumeration.py`(`external_id_collision` を `ConnectorError` で送出)・`crawl/` が `failed` にする |
| 4 | 「削除中」は `loreley-sources.status=deleting`(CA-P-35) | `sources/source_store.py`(`mark_deleting`・`delete` は `status=deleting` のときだけ)・`source_delete/` |
| 5 | 連続スキップは取得段階と登録段階の別カウンタ(CA-P-20) | `crawl/skip_counter.py`・`crawl/outcomes.py` |
| 6 | ソース削除の順1・2・4の送信前にメンテナンスフラグを確認し、立っていれば `failed`(`maintenance`)(CA-U-17) | `source_delete/executor.py`・`indexer_calls.py` の確認点(`Check.OWNERSHIP | Check.MAINTENANCE`)。順3・5はフラグ対象外(0019 §1) |
| 7 | 設定項目は必須・既定値なし・全置換、`connector_type` は変更不可、削除中の設定の更新は409(CAPI-P-7・9)。メンテナンス中の登録・更新・取り消し・解放はフラグを確認しない(CAPI-P-17) | `sources/`(更新・登録)・`api/request_parsing.py`・`api/responses.py` |
| 8 | 識別子エラーは `partially_succeeded`、原本サイズ超過は別記録でジョブ status に影響しない(CA-P-25・23) | `crawl/`(`outcomes.py`・`run.py`・`executor.py`) |
| 9 | `follow_symlinks`・`include_hidden` は両方 `false`、`title` はファイル名のみ(CFS-U-2・3 相当) | `connectors/filesystem/settings.py`・`config.py`・`fetch.py` |
| 10 | 0件列挙は現状維持(警告のみ。CA-P-52) | `crawl/` の `finalize_registration`・`warning_log.py` |
| 11 | CM-U-4: SIGTERM 時は実行中ジョブの完了を待たず終了処理もしない。次回起動時の回復で `failed(crawler_restart)` | `main.py`(`stop_components`)・`jobs/recovery.py`(接続も閉じない) |
| 12 | CA-U-3: メンテナンスフラグの書き込みは運用者の手動手順。Crawler は読み取りのみ | `jobs/records/maintenance_flag.py`(読み取り専用・fail-closed)・README 6章 |

## 3. 実装者が決めた内容・設計書にない決定(「決めてよい事項」)

0002 §4.1 の範囲。決めたら作業記録に残す規定のため、決定の出所を併記。

- 同期 HTTP クライアントは **urllib3**(CM-U-2。`DELETE` にボディ可・API ごとのタイムアウト・スレッドセーフ・opensearch-py の既存依存)(0006)
- CM-U-9 の仮置き(a): Indexer の上限は `LORELEY_CRAWLER_INDEXER_<名前>`。未設定は警告して検査省略(0005・0017)
- `owner` は環境変数 `LORELEY_CRAWLER_OWNER` で必須(未設定は起動失敗。256バイト以内・制御文字なし)(0017)
- 全件走査のタイブレークは呼び出し側が `sort` に一意な `document_id` で終える方式。ソース削除の順3は「全件走査+バルク削除」(条件指定削除は置かない)(0006・0010)
- 文書単位とリクエスト単位のリトライ回数は別枠(各3回)。連続スキップの計数は再送を終えてからバッチの文書順(0013 §4)
- ロック解放の順序はロック削除(版条件)が先・ジョブ `failed(lock_released)` が後。最終状態を記録できなかったときは Runner がロック文書を削除しない(0011 §4)
- `finish_notice` は `{content, send_started_at}`。終了通知の送信前に所有・取り消し・メンテナンスを確認し、件数の不変条件(`enumerated_count` = 登録+スキップ+サイズ超過)を整理の前と送信前に確認(0014・0015)
- 整理は種別ごとの判定(skip は今回スキップした文書のものだけ、oversize は今回サイズ超過だった文書のものだけ残す)(0015)
- 設計書にない区分(`StoreUnexpectedResponseError`・`IndexerRejected("malformed_response")`・`search_incomplete`・`pit_expired` など)は安全側(`failed`)に倒す(0006・0007)
- glob 照合は正規表現のバックトラックを使わない多項式時間の実装(ReDoS 対策。`max_double_stars` は削除)(0009)
- 起動順に「ログの設定」「未設定 Indexer 上限の警告」を追加、停止時に OpenSearch・Indexer の接続を閉じない、SIGTERM の再送出を無害に受けるハンドラ(0018・0019)
- 索引名が同じなら起動失敗(設計書にない追加の安全策)、HTTP 待ち受けの既定 `127.0.0.1:8001`、ジッタ割合0.2(0017)

## 4. 仮値一覧(設定可能。環境変数と既定値の全表は 0017 §5・`apps/crawler/README.md` 4章)

| 設定 | 既定値 | 出所 |
| --- | --- | --- |
| Store 層タイムアウト / ハートビート専用 | 30秒 / 10秒 | architecture 11章の空欄を仮置き(0006) |
| 全件走査(ページ・PIT 保持・検索タイムアウト)・バルク削除 | 1,000 / 60秒 / 60秒 / 1,000 | architecture 11章の値 |
| Indexer API ごとのタイムアウト | connect 10秒、開始・終了・Status 30秒、last-seen 60秒、バッチ 300秒、削除1〜3 600/4,200/60秒 | architecture 11章 |
| リトライ | 最大3回、初期1秒、倍率2、上限30秒、ジッタ0.2 | 11章・実装(ジッタ0.2は仮値) |
| チャンク・last-seen・バッチ | 500 / 500 / 20文書 / 32MiB | 11章 |
| 連続スキップ・識別子エラーの例 | 20 / 20 | 11章 |
| 終了通知の ID 一覧の警告閾値・ポーリング | 8,000 / 5秒・30分・失敗連続3回 | 11章 |
| `warnings` の上限・過去ジョブ件数 | 20 / 10 | 11章・実装 |
| ハートビート | リース300秒・更新100秒・失敗時再試行10秒・停止の待ち30秒(停止の待ち ≥ 専用タイムアウトの2倍) | 実装(0010)・整合性検査(0017) |
| Job Runner 走査間隔・受付途中の猶予 | 5秒 / 60秒 | 実装(0011)・11章 |
| Scheduler 判定周期 | 30秒 | 実装(0016) |
| 原本1件の上限・列挙の上限・表示の長さ | 20MiB / 500,000 / 200文字 | 11章 |
| FS(パターン数・長さ・読み取り単位・説明文のパス) | 100 / 1024バイト / 1MiB / 200文字 | 実装(0008) |
| HTTP 待ち受け | `127.0.0.1:8001`(コンテナでは `0.0.0.0`) | 実装(0017) |
| 停止の時間(**環境変数ではなく `main.py` の固定値**) | uvicorn graceful 10秒・join 5秒×2 | 実装(0018) |
| Dockerfile `HEALTHCHECK` | interval 15s・timeout 5s・retries 3・`--start-period` 180秒 | 実装(0020。実測ではない) |

## 5. 設計書の改版依頼リスト(提案。設計書は変更していない)

本タスクで変更した設計書は、**P0 の新版4ファイル**のみ(crawler-api v0.3・architecture v0.3・module-structure v0.4・decisions v0.3。`/healthz` を置くことをユーザー回答で確定、0003・0004)。実装で決めた内容の改版依頼は、次の作業記録に集約されている: 0007 §4-8(区分の追加)、0008 §8・0009 §6(connectors・documents・glob)、0010 §7(sources・locks)、0011 §8・0012 §5(jobs)、0013 §9・0014 §5・0015 §5(crawl)、0016 §6(source_delete・scheduler)、0017 §8(api・config)、0018 §7(main)、0019 §4(SIGTERM・メンテナンスフラグの結論・停止の時間予算など)、0020(HEALTHCHECK の採用値 180秒)。

特に重要なもの: (a) メンテナンスフラグの範囲の結論(順1・2・4の前だけ確認、順3・5は対象外。0019 §1)、(b) 停止の時間予算と compose の `stop_grace_period`(30秒以上が目安。0019 §4-4)、(c) 件数の不変条件の確認位置(整理の前。0015 §5)、(d) 整理の種別ごとの判定(0015 §5)、(e) 更新(PUT)で `api` が保存済み設定を読む設計(0017 §3-2)、(f) 本文サイズの上限は規定なし。

## 6. 持ち越し(単体テストでは検証していない。README 8章・9章)

- **実 OpenSearch が必要**: `create` と `if_seq_no` の並行時の原子性、opensearch-py のスレッド安全性(CM-U-1)、10,001件以上の走査・PIT・refresh・バルク削除の部分失敗(#37)、`allow_partial_*` のサーバー側の受理、PIT 期限切れの実機の応答形、実環境の date 型ソート・絞り込み、メモリ上 Repository が再現しない `non_unique_sort`
- **実 Indexer が必要**: Status 項目(`finish_received_at`・`waiting_for`)の出方、終了通知の409、ポーリング間隔・30分の妥当性、`document_id` 照合(CM-U-3)、`FakeIndexerClient.delete_*` が `lock` の値を検証しないこと、**件数照合の独立検証**(Indexer 側 N_seen+E_missing)
- **実機の FS**: NFS/SMB・Docker バインドマウントの errno・マウント外れ・`st_ino`・取得中変更、ブロッキング I/O 中のスレッド・GIL 保持中のハートビート(CFS-U-4)、実運用イメージの FS エンコーディング・`:ro`
- **実コンテナ・compose**: 実 OpenSearch・実 Indexer と接続し実行中ジョブがある状態での `docker stop` の所要時間、`/healthz` の `healthy` 化
- **スコープ外(別タスク。0003・ユーザー回答)**: infra 前提作業(`loreley-sources` の索引定義とマッピング案(architecture 3.1 の表 CA-P-49)、`jobs.json` の拡張(Indexer 結合テストと共有。Indexer が読む4項目の型は維持)、`init-indices.sh`、既存索引への反映、compose の `crawler` サービス(`opensearch-init` 完了待ち・Indexer の上限値の受け渡し・`:ro` マウント・ヘルスチェック・`stop_grace_period`・`JOBS_INDEX_NAME` の同値化))、OpenSearch の `action.auto_create_index` の判断(0006 §6)、Integration Test。**infra 前提作業が済むまで、実 OpenSearch ではジョブ・ロックの検索・並べ替えが正しく動かない**(README 9章)。別タスクの起票は「今は起票しない」(ユーザー回答 2026-11-13)

## 7. ユーザー判断待ち・未了

- 設計書(Crawler の architecture・api・module・decisions v0.2〜新版、connector v0.2)のユーザー承認と、decisions 4章の「ユーザー判断待ち」10件の最終確定(案どおり実装しているが**未承認のまま**)
- infra 前提作業の別タスク起票の要否(ユーザー回答: 今は起票しない)
- コミット(ユーザー指示があるときのみ。`apps/crawler/`・`docs/v0.x/system-design/crawler/` の新版4ファイル・`agent_tasks/20261113_implement_crawler/` が未コミット)

## 8. 作業の経過(参考)

要件確認 0001 → プラン 0002 → プラン承認と `/healthz` 追加 0003 → P0 設計書の新版 0004 → P1 0005 → P2 0006・レビュー 0007 → P3 0008・レビュー 0009 → P4 0010 → P5 0011 → P4+P5 レビュー 0012 → P6a 0013 → P6b 0014 → P6 レビュー 0015 → P7 0016 → P8a 0017 → P8b 0018 → P7+P8 レビュー 0019 → P9 0020。テスト数の推移(pytest): 335 → 794 → 1395 → 1488 → 1891 → 2161 → 2217 → 2414 → 2516 → 2583 → 2769 → 3153 → 3199 → 3249。

留意: 実装担当(`code-implementer`)の最終報告が `SubagentHandback` の制限でメインに届かなかった場面(0007・0009)があり、その場合はディスク上の状態・再レビューで確認した。メインは各フェーズで検証コマンドを自分で再実行し、報告と一致することを確認した。

## 9. 次のアクション

task-reviewer(0002 §8)でタスク全体を確認し、指摘に対応してからユーザーに完了報告する。

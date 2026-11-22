# タスク状態

## 基本情報

- 状態: done
- 現在工程: なし(未決事項の対話による解消と反映まで完了。ユーザー確認事項あり)
- 最終更新: 2026-11-16
- 最新作業記録: 0026-fix-unknown-deletion-status.md

## 現在の状況

- 要件確認(0001)、プラン(0002、ユーザー承認済み 2026-11-13)、プラン更新(0003: `/healthz` 追加)完了。
- **P0 完了**(0004): `/healthz` 追加のため設計書の新版4ファイルを作成(crawler-api v0.3、module-structure v0.4、architecture v0.3、decisions v0.3)。document-reviewer 2回目で指摘なし。確定は「ヘルスチェック用の API を置く」だけで、パス・応答・動作・HEALTHCHECK は案。**以降の実装の正本は新版**(connector 関連は v0.2 のまま)。
- 開始時点 HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(P1〜P2 のレビュー比較基準)。uv 0.13.8、Docker 20.10.13 が使える。
- **P1 完了**(0005): `apps/crawler/` を新規作成(設定ファイル、全モジュールの空パッケージ、`common/`、`config.py` の整合性検査の純粋関数、`tests/fakes/clock.py`、依存ルール検査)。メインが再実行: pytest 335 passed、ruff check・format 成功。P1 単独のレビューはなし(P2 後に P1+P2 をまとめてレビュー)。
- **P2 完了**(0006): `infrastructure/opensearch`(Repository、PIT+search_after の全件走査、バルク削除)・`infrastructure/indexer_client`(urllib3。HTTP クライアント選定、#17 の DELETE ボディ確認済み)、fakes、Indexer 契約表(api v0.10 と apps/indexer に食い違いなし)。メインが再実行: pytest 794 passed、ruff・format・uv lock --check 成功。設計書にない区分(`StoreUnexpectedResponseError`、`IndexerRejected("malformed_response")`)を追加、P4・P5 に要周知。
- **P1+P2 のレビュー完了**(0007): code-reviewer・test-reviewer が各2回(Critical なし。Important 6件は全て解消、最終は「軽微な修正で可」で小修正も対応済み)。主な修正: 全件走査・一覧の部分失敗/timed_out の検出(`search_incomplete`)、PIT 期限切れの分類、fake の忠実度(Indexer 検証・Status・`Conflict`)、PIT 隔離と `search_after` のテスト強化。メインが再実行: pytest 914 passed、ruff・format・uv lock --check 成功。
- **P3 完了・レビュー完了**(0008・0009): `connectors`(interface・filesystem・レジストリ)と `documents`。code-reviewer・test-reviewer のレビューと修正を経て、最終は code-reviewer「可」(指摘なし)・test-reviewer の Important は全て解消。主な修正: glob 照合を正規表現から多項式時間のアルゴリズムに置き換え(ReDoS 対策。`max_double_stars` は削除)、想定外の例外の変換を `from None`(R11)、取得の後処理も例外変換の範囲に、テストの検出力強化(NFC・多セグメント exclude・scandir の開閉・サイズだけの変更)。メインが再実行: pytest 1488 passed・3 skipped(macOS 固有の3件。Linux Docker では非 root で skip 0)、ruff・format・uv lock --check 成功。
- **P4 完了**(0010): `sources`(`SourceReader`/`SourceStore`)、`jobs/records`(ジョブ・スキップ・サイズ超過記録、メンテナンスフラグ、整理・一括削除)、`jobs/locks`(ロック・ハートビート)を実装。メインが再実行: pytest 1891 passed・3 skipped、ruff・format・uv lock --check 成功。P4 のレビューは P5 完了後に P4+P5 をまとめて実施。**P5 以降への申し送りは 0010 §5**(P5 の依頼に必ず含める)。
- **P5 完了・P4+P5 のレビュー完了**(0011・0012): `jobs` 直下(受付・取り消し・ロック解放・起動時回復・Job Runner・`JobContext`)を実装。レビューで Important 3件を修正(最後の手段の `failed` が終端ジョブを上書きする欠陥、空の `job_id` の `fetch("")` が実機で `ValueError`、`parse_instant` の `OverflowError`)。最終は code-reviewer・test-reviewer ともに「軽微な修正で可」、残り(回復の形式不正ジョブ記録)も修正済み(再レビュー省略、理由は 0012 §3)。メインが再実行: pytest 2217 passed・3 skipped、ruff・format・uv lock --check 成功。**P6 以降への申し送りは 0012 §6・0011 §6**(P6 の依頼に必ず含める。特に `jobs` 入口に `Repository` を見せないファサードが要る点、`finish` の False の意味、`changes` は JSON 型)。
- **P6a 完了**(0013): `jobs` 入口のファサード(`DocumentRecords`・`JobHistory`)と `crawl` の実行開始〜チャンク処理(開始通知・`last-seen`→取得→バッチ登録・リトライ・スキップ・連続スキップ・`document_id` 照合・整理)を実装。メインが再実行: pytest 2414 passed・3 skipped、ruff・format・uv lock --check 成功。`CrawlExecutor.__call__` は 6b まで未完成(`NotImplementedError` で最後の手段の `failed(internal_error)` に落ちる。安全側)。**6b への申し送りは 0013 §6、P7・P8 へは §7**。P6 のレビューは 6b 完了後にまとめて実施。
- **P6b 完了**(0014): `crawl` の終了通知(内容の固定・`send_started_at`・送信)、ポーリングと確認結果の区分、最終状態、異常系の最終対応(`OwnershipLost`→`lock_lost` ほか)、0件列挙警告・`warnings` を実装し、`CrawlExecutor` を完成。メインが再実行: pytest 2516 passed・3 skipped、ruff・format・uv lock --check 成功。P6 全体の code + test レビューは実施中(重点: 削除に関わる安全側、特に 0014 §4-1 の「ロック喪失時も `failed` 通知を送る」設計書どおりの実装の安全性)。**P8 への申し送りは 0014 §6**、設計書改版依頼は 0013 §9・0014 §5。
- **P6 全体のレビュー完了**(0015): code-reviewer・test-reviewer が各2回。Critical なし、test の Important 4件(終了通知の送信直前の所有確認、`force_delete`/`rewrite_mode` の取り違え、`crawl_id`、ID 一覧閾値の合算)を修正。0014 §4-1(ロック喪失時も `failed` 通知を送る)は `apps/indexer` の実コードで確認し**安全・変更不要**。件数の不変条件を終了通知の送信前に確認(整理の前に置く)、整理を種別ごとの判定に、fake を実 Indexer に合わせた。メインが再実行: pytest 2583 passed・3 skipped、ruff・format・uv lock --check 成功。**P7・P8 への申し送りは 0015 §6**、設計書改版依頼は 0013 §9・0014 §5・0015 §5。
- **P7 完了**(0016): `source_delete`(順0〜6。所有喪失・メンテナンス・Indexer 拒否で後続の削除を行わず `failed`、順5は `status=deleting` のときだけ)と `scheduler`(周期起動、拒否は見送り・取り返さない)を実装。メインが再実行: pytest 2769 passed・3 skipped、ruff・format・uv lock --check 成功。P7 のレビューは P8 完了後に P7+P8 をまとめて実施(code-reviewer 省略不可。重点: **メンテナンスフラグの範囲(順3・5は対象外=設計書どおり。0016 §3)**、起動順・停止順、ログ流出)。**P8 への申し送りは 0016 §5**、設計書改版依頼は 0016 §6。
- **P8a 完了**(0017): `api`(Admin API 6エンドポイント+`GET /healthz`)と `config.py`(環境変数の読み込み・整合性検査・`ConfigError`)を実装。メインが再実行: pytest 3153 passed・3 skipped、ruff・format・uv lock --check 成功。**メインの依頼文の誤り(設定更新はメンテナンス中409)を実装担当が設計書(CAPI-P-17)どおりに正した**(0017 §0)。環境変数一覧は 0017 §5(README 用)。**8b への申し送りは 0017 §6**、設計書改版依頼は 0017 §8。P7+P8 のレビューは 8b 完了後。
- **P8b 完了**(0018): `main.py`(composition root。起動順 設定→ログ→警告→バックエンド→組み立て→回復→Runner→Scheduler→アプリ→uvicorn、アプリは回復後に作る。停止は Scheduler→Runner の `request_stop` と join、実行中ジョブは待たず終了処理もしない)を実装。メインが再実行: pytest 3199 passed・3 skipped、ruff・format・uv lock --check 成功。**P7+P8 の code + test レビューは実施中**(データ削除を含むため code-reviewer 省略不可。重点: メンテナンスフラグの範囲 0016 §3、起動順・停止順、ログ流出、`api` の更新時 `connector_type` 読み取り 0017 §3-2)。設計書改版依頼は 0016 §6・0017 §8・0018 §7。
- **P7+P8 のレビュー完了**(0019): code-reviewer(2回)・test-reviewer(1回)。Critical なし。**メンテナンスフラグの範囲は設計書どおり(順1・2・4の前だけ)でよい、停止時に接続を閉じない判断は妥当**(0019 §1)。Important を修正: SIGTERM で `main()` の `finally` が走らない(uvicorn の再送出)→ `uvicorn.run` の前後だけ無害なハンドラを入れて解消(実プロセスで検証、データ安全性は不変)、秘密マスキングの配線・実 uvicorn の起動停止・順2の最中のフラグ・`delete-jobs` の `source_id` 検証のテスト追加。メインが再実行: pytest 3249 passed・3 skipped、ruff・format・uv lock --check 成功。**停止の時間予算が Docker 既定の停止猶予10秒を超えうる→README に `stop_grace_period` の注意(0019 §4-4)**。設計書改版依頼は 0019 §4。
- **P9 完了・最終整理**(0020・0021): `Dockerfile`・`README.md` を作成し、code-reviewer(Dockerfile。実機で PID 1 の `docker stop`=終了コード0 を確認)・document-reviewer(README。環境変数64項目を機械照合)のレビュー指摘に対応。メインが再実行: pytest 3249 passed・3 skipped、ruff・format・uv lock --check 成功、`docker build` 成功・起動確認(fail-fast・非 root)一致。Linux(Docker)非 root で 3255 passed・skip 0。**完了条件1〜10の検証結果・採用案一覧・仮値一覧・決めた内容・持ち越し一覧は 0021**。タスクレビューは実施中。
- **タスクレビュー完了**(0022): task-reviewer「軽微な修正で可」(Critical なし、Important 1件=持ち越し・既知の限界の取りこぼし)。メインとは独立に pytest 3249 passed・3 skipped、ruff・format・uv lock --check、docker build・fail-fast を再確認。スコープ(infra・compose・apps/indexer・旧版 docs)は無変更、確定扱いは `/healthz` を置くことだけ。指摘に対応: README 10章に既知の限界を追記、設計書改版依頼に追加(0022 §3)、独立レビュー未実施の箇所を記録(0022 §4)。**タスクは完了。ユーザー判断待ちの事項は下記**。
- **後続フェーズへの申し送りは 0007 §4**(sort は一意な `document_id` で終える、`pit_expired` は `with scan` 全体をやり直す、リトライ後の `AlreadyExists`/`Conflict` は所有者を読み直す、など)。P4・P6・P7 の依頼に必ず含める。
- `apps/crawler/` は未コミット(コミットはユーザー指示があるときのみ)。

- **設計書の承認と改版の反映**(0023。ユーザー指示 2026-11-16「未確認事項について、設計書は承認する。2設計書の改版に反映する。それ以外は別タスク」): 設計書の現行版全体を承認(`-P-` は承認済みの案。`-K-` への付け替え・仮値の確定はしない。ID 列=decisions v0.3 の4章の10件+CM-U-4・CA-U-3 以外の `-U-` は未決のまま)。改版依頼(0021 §5・0022 §3 ほか)を新版に反映: `crawler-architecture-v0.4`・`crawler-api-v0.4`・`crawler-module-structure-v0.5`・`crawler-design-decisions-v0.4`・`connector/connector-file-system-v0.3`・`connector-interface-v0.3`・`connector-web-v0.3`(旧版は無変更)。document-reviewer 2回(Critical なし。Important は反映済み)。README の設計書参照・承認の記述・2か所の誤り(フラグの確認位置、形式不正ロックの解消手段)を修正。**実装コード・infra は変更なし。以降の設計の正本は上記の新版**。3〜5(infra 前提作業の起票・コミット・Integration Test)は「それ以外は別タスク」で、本タスクでは何もしていない。

- **PR レビュー指摘への対応**(0026): Status API の応答の `status` が契約外の値のとき `confirmed` になる問題を、応答の解析で契約違反にして修正(pytest 3331 passed)。
- **未決事項の対話による解消と反映**(0025。ユーザー指示 2026-11-16「未決事項は一件ずつインタラクティブに質問」): 12件を質問して回答済み(周期は cron 式・止まっていた分は起動しない、CA-U-13・5・4 残り・9・14 Crawler 側・CAPI-U-2・4・7・8 残り・CI-U-4・6 ほか)。実装は cron 式への置き換え(`schedule_cron`、`LORELEY_CRAWLER_TIMEZONE`、`cronsim` 追加、Scheduler の `last_checked` 方式)で、pytest 3321 passed・3 skipped、ruff・`uv lock --check` 成功、code-reviewer の Important(夏時間で同時刻が繰り返し起動)を修正済み。設計書7本を追補(その場で更新)し、document-reviewer・code-reviewer の指摘を反映済み(再レビューは省略。メインが機械照合)。なお未決は実測後・実機確認・Admin API/Web の設計時・infra の別タスクの性質のもの。
- **0023 の確認へのユーザー回答の反映**(0024): 承認の範囲の解釈は「上の解釈で良い」。CA-U-20(専用の復旧経路を置かない)・CAPI-U-11(int64 範囲外は考えない)・CAPI-U-12(リクエスト本文の上限 10 MiB・仮値)を解消し、設計書の新版にその場で追補。**実装は本文の上限だけ追加**(`api/request_body.py`、テスト +6)。pytest 3255 passed・3 skipped、ruff 成功。レビューは省略(理由は 0024 §4)。

## 次のアクション

- なし(完了)。別タスク(infra 前提作業・Integration Test・コミット)は、ユーザーの指示があるまで着手しない

## 未解決事項

- なお未決(2026-11-16 の対話の後。質問しても決まらない性質のもの。一覧と残る論点は decisions v0.4 の5章): 実測後(CA-U-1・CAPI-U-10・CFS-U-6・CM-U-6。CI-U-3 の数値)、実機でしか確認できない(CA-U-10・CM-U-1・CFS-U-4・CA-U-18)、Admin API・Web の設計時(CA-U-12・CAPI-U-1・3 の残り・5・6)、Web Connector の設計時(CM-U-8・CI-U-5・7・8・9・10・11・CW 系)、infra の別タスク(compose で Indexer の上限を渡す定義。CA-U-14 の運用部分)
- 提案のままでユーザー未確認(0025 末尾): `LORELEY_CRAWLER_TIMEZONE` の名前、`@daily` などの別名を受け付けないこと、cron 文字列の絞り込み(空白1つ区切り・512文字以内)、Scheduler の判定時刻の進め方(一覧の失敗では進めず・受付の例外では進める)、時計が戻った tick は起動しない。Crawler の再起動中に過ぎた cron の時刻は起動しない
- `/healthz` が `healthy` になる実機確認は Integration Test(スコープ外)に持ち越し。実機でしか確認できない項目(0002 §10、0007 §5、README 8章)も持ち越し
- 0015 §3(件数の不変条件の整理前への移動)は独立レビュー未実施(0022 §4)
- infra 側の判断事項(別タスク向け): OpenSearch の `action.auto_create_index` の無効化(0006 §6)

## ユーザー判断待ち

未回答の判断は承認扱いにしない。

1. (解決済み)「10M」は 10 MiB とユーザーが確認(2026-11-16)
2. **提案のままの細部の確認**: 上の「未解決事項」の「提案のままでユーザー未確認」(cron 式の細部)。違う場合は設計書・実装を直す
3. **別タスク(ユーザー指示 2026-11-16「それ以外は別タスク」)**: infra 前提作業(`loreley-sources` の索引定義・`jobs.json` の拡張・`init-indices.sh`・compose の `crawler` サービス・`stop_grace_period` 30秒以上など。これが済むまで実 OpenSearch ではジョブ・ロックの検索・並べ替えが正しく動かない。README 9章)、Integration Test、コミット(`apps/crawler/`・設計書の新版・`agent_tasks/20261113_implement_crawler/` が未コミット)。起票・実施は未着手

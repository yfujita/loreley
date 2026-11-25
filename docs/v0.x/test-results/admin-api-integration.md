# Admin API 結合テスト(compose + 実 OpenSearch + 実 Indexer + 実 Crawler + 実 api)の結果

| 項目 | 内容 |
| --- | --- |
| 状態 | **実施済み**(2026-11-25。23 件。P4 完了時点でクリーンな状態から 2 回連続で全件成功。P5 の修正後も 2 回連続で全件成功。レビュー指摘への対応後も 2 回連続で全件成功(計 8 回の実行、成功 6 回)。実行中のホストのスリープ(推定)で 1 回失敗、待ちの不足で 1 回失敗した(いずれも原因と対処を 4.6 に記載)。未検証事項は 7 章、申し送り項目別の判定は 4.4) |
| 作成日 | 2026-11-25 |
| 参照する設計書 | `docs/v0.x/system-design/api/admin/admin-api-v0.1.md`(EP-01〜14、2.5〜2.9、10 章)、`admin-api-architecture-v0.1.md`(AAA-P-6、AAA-U-1〜3・7・10)、`docs/v0.x/system-design/api/api-base-design-v0.1.md`(8 章 compose、9.2 の HO-34・35・40・41・43・44・45)、`docs/v0.x/system-design/crawler/crawler-architecture-v0.4.md`(3.3、5.1、7.5〜7.8、8.1)、`crawler-api-v0.4.md`、`docs/v0.x/system-design/indexer/indexer-architecture-v0.10.md`(9.2・9.3・9.7)。**略号**(テストの docstring や設計書の表記): A=`api-base-design-v0.1.md`、B=`admin-api-v0.1.md`(「B 8.1」は B の 8.1 章)、C=`admin-api-architecture-v0.1.md`、D=`admin-api-module-structure-v0.1.md`、E・F=`docs/v0.x/system-design/ui-admin/frontend/` の `ui-admin-frontend-architecture-v0.1.md`・`ui-admin-frontend-module-structure-v0.1.md`(A は `system-design/api/`、B〜D は `system-design/api/admin/` にある)。4.4 の「0021 B 章」は、作業記録 0021 の B 章(申し送り)で、設計書 B とは別 |
| 関連 | `tests/integration/api/README.md`(実行・シナリオ一覧)、`deploy/compose/README.md`(起動・公開範囲の注意)、`docs/v0.x/test-results/crawler-integration.md`・`indexer-integration.md`(同種の記録)、`agent_tasks/20261125_create_it_for_admin_api/`(作業の経緯。0004〜0008 が各フェーズの一次記録)、`agent_tasks/20261123_implement_admin_api/0021-task-review-and-handoff.md` の B 章(申し送り元)・`0018`(手動スモーク) |

## 1. 目的

Admin API(`apps/api`)を compose で起動し、実 OpenSearch・実 Indexer・実 Crawler(別コンテナ。mock にしない)に対して HTTP で呼び、単体テストでは確認できなかった挙動を実機で確認する。具体的には、実 Crawler への中継、実 OpenSearch へのクエリの意味、実行中ジョブがロックを持つ間の状態、実コンテナの停止と復旧。あわせて、`agent_tasks/20261123_implement_admin_api/0021` の B 章(結合テストへの申し送り)を、確認済み・一部確認・未検証に仕分ける(4.4)。シナリオの内容と実行方法は `tests/integration/api/README.md` を正とし、ここには複製しない。

## 2. 記録のルール

- 実際に実行・確認した結果だけを書く。推測や期待値を結果として書かない。推測は「推測」と書く。
- 未検証の項目は「未検証」(テストを作っていない、または実機で見ていない)、記録がなく確認できない項目は「未確認」と書く。
- **設計が値を定めている箇所**の実機の値は設計と照合する。**設計が値を定めていない(複数の値を許す)箇所**の実測値は、食い違いではなく観測値として区別して書く(5 章)。
- 再実行は、上書きせず新しい行・節として追記する。
- 設計書の内容は複製せず、参照だけにする。結果が設計書の変更を要する場合は、9 章に書き、反映はユーザーが判断する。

## 3. 環境と実行条件

| 項目 | 内容 |
| --- | --- |
| 実施日・実施者 | 2026-11-25。Claude Code(実装は `code-implementer`、静的検査・残骸の確認はメインエージェント)。ユーザーの指示のもとで実施 |
| ブランチ・コミット | `feature/create-it-for-admin-api`。ブランチ作成時の基準は `55dce2f`。P1〜P5 の各フェーズとレビュー対応はコミット済み(P4 は `abceb9c`、P5 は `d3250ee`。レビュー対応は後続のコミット)。本書・README は P5 で作成し、レビュー指摘への対応で更新した |
| ホスト | macOS(x86_64。`uv --version` の出力が `x86_64-apple-darwin`)。compose v2.3.3(0008)、uv 0.13.8。CPython は 3.13.4(pytest の実行ログの `platform` 行。`tests/integration/api/results/` の 15 本すべてで同じ)。Docker のバージョン・Docker VM のメモリは、本タスクでは**記録していない**(既存の IT の記録は Docker 20.10.13・VM 約 3.84GiB。同じホストと推測するが未確認) |
| pytest | `uv.lock` で固定: pytest 9.2.0、httpx 0.28.1(15 パッケージ)。`requires-python` は `>=3.12,<3.14` |
| OpenSearch | `opensearchproject/opensearch:3.9.0`(compose の既定。`deploy/compose/.env` は存在せず、スクリプトはバージョンを設定しないので既定のままと考えられる。実行時のタグは確認していない)。単一ノード |
| 実行方法 | `scripts/run-api-integration-test.sh`(`-p loreley-it`。`up -d --build opensearch opensearch-init indexer crawler api` + 自前ポーリング → pytest(`-v -rP`) → `down -v --remove-orphans` と `tests/integration/api/data` の削除) |
| compose の構成 | `deploy/compose/compose.yaml` に `api` を追加(P1。HO-34・35・43・44)。ホストへの publish は `127.0.0.1:8080` のみ。`depends_on` は `opensearch`(healthy)と `opensearch-init`(正常終了)のみ。共通変数(索引名 4・cron のタイムゾーン・猶予)を Crawler・Indexer・api に同じ変数から渡す。検索エイリアスには実体名を渡さない |
| テスト用の設定 | `tests/integration/api/compose.test.yaml`: Crawler のポーリング間隔 **10 秒**(Crawler IT は 2 秒)・ポーリング上限 120 秒・Job Runner の走査間隔 1 秒、Indexer の削除ワーカーの走査間隔 **5 秒**(既定 2 秒)、原本の上限 64 KiB(Indexer・Crawler・Crawler の検査値の 3 か所で同値)、Crawler を `127.0.0.1:8001` に publish(診断用。テストは Crawler API を直接呼ばない)、api に `fixtures/web/index.html` だけのディレクトリを `/app/web` に mount(EP-13 の `web` を `normal` にするため)、`crawler`・`api` の healthcheck の間隔 3 秒(`crawler` の `start_period` は 180 秒) |
| スクリプトが固定する値 | ホスト側ポート 9200・8000・8001・8080、索引名 4 つ(既定値)、`LORELEY_CRON_TIMEZONE=Asia/Tokyo`(既定 UTC と違う値にして、共通変数が届くことを AIT-01 で確認する)、`LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` |
| 起動所要時間・メモリ | 起動の所要時間の内訳とメモリ使用量は**測定していない**(所要時間は 6 章) |

## 4. 結果

### 4.1 実行回ごとの結果

記録のあるフェーズ末の実行。いずれも `--keep` なしで、`down -v` 済みのクリーンな状態から実行した。

| フェーズ | 実行 | 結果 | 所要時間(pytest / スクリプト全体) |
| --- | --- | --- | --- |
| P2(0005) | AIT-01 のみ(`-k test_01`) | 5 passed、終了コード 0 | 初回ビルド込みで約 4〜5 分(スクリプト全体) |
| P3a(0006) | 全件(12 テスト) | 12 passed、終了コード 0 | pytest 56 秒 |
| P3b(0007) | 全件(20 テスト)を 2 回連続 | どちらも 20 passed、終了コード 0 | pytest 171.5 秒・172.4 秒 / スクリプト全体 248 秒 |
| **P4(0008)** | **全件(23 テスト)を 2 回連続** | **どちらも 23 passed、終了コード 0**。不安定なテストなし | pytest 344.8 秒・342.8 秒 / スクリプト全体 6 分 58 秒 |

- 途中の `--keep` 反復で、P3a に 1 件失敗した(EP-03 直後の EP-01 でソースが見えない。検索で読む EP の反映遅れ。原因はテスト側の待ち不足で、上限つきの待ちを足して解消。アサートの値は変えていない)。アプリの不具合ではない
- どの実行も、終了後に `loreley-it` のコンテナ・ボリューム・ネットワーク・`tests/integration/api/data` が残っておらず、ポートが空き、`docker ps -a` に他プロジェクトのコンテナ(`opensearch-opensearch-1`。停止中)以外が増えていないことを、メインエージェントが確認した(0005〜0008)
- 2 回連続の実行は、毎回 `down -v` 済みのクリーンなスタックで実行しているため、実行間の干渉がないことの根拠にはならない。1 回の実行の中のテスト間の干渉は、`source_id` をテストごとに一意にし、各テストの前後でジョブのアイドルを待つことで避けている

### 4.2 起動確認(AIT-01。実機の値)

| 項目 | 結果 |
| --- | --- |
| 起動 | `opensearch`・`indexer`・`crawler`・`api` が healthy、`opensearch-init` が Exited(0)。`/healthz` が 200 |
| EP-13 | 8 件が固定順(crawler・indexer・opensearch・api・web・opensearch-dashboards・embedding・llm)。crawler・indexer・opensearch・api・web が `normal`、他 3 つが `not_configured`(`reason` はすべて null)。`web` はテスト用の mount が効いている |
| EP-14 | `cron_timezone=Asia/Tokyo`、`dashboards_url=null`(共通変数 `LORELEY_CRON_TIMEZONE` が api に届いている) |
| EP-12 | `loreley-documents-000001`・`loreley-deletions`・`loreley-jobs`・`loreley-sources` を含む。他の索引が共有されても壊れないよう、4 索引の部分集合として確認 |
| OpenAPI | `/api/admin/v1/openapi.json` は 404(`OPENAPI_ENABLED` は既定の無効) |

### 4.3 シナリオ別の結果(23 テスト)

すべて passed(4.1 の P4 の 2 回)。「備考」は実機の観測値。**設計との食い違いはなかった**(5 章)。

| ID | シナリオ | 結果 | 備考(実測値) |
| --- | --- | --- | --- |
| AIT-01 | 起動疎通(5 テスト) | passed | 4.2 のとおり |
| AIT-10 | 登録・更新・一覧・詳細 | passed | EP-03 は `ttl_days=2`・`ratio_threshold_percent=12.5` を `ttl=172800`・`ratio_threshold=0.125` で `loreley-sources` に保存。更新後(3600 秒・20%)は `ttl_days=null`。同内容の再送は 200、内容違いは 409 `source_already_exists` |
| AIT-11 | 実 Connector の違反(2 パラメータ + 更新の 1 件) | passed | 相対 `root`: field=`connector_config.root`・detail「`/` で始まる絶対パスでない」。未知項目: field=`connector_config`・detail「未知の項目がある」(設計 2.5 の分解どおり)。保存されない |
| AIT-12 | 未登録ソース | passed | EP-04・05・06 は 404 `source_config_not_found`、EP-02・11 は 404、EP-08 は 200 `released=false` |
| AIT-20 | クロールの起動から完了まで | passed | 実行中の窓で EP-02 `held_crawl`、EP-09 の実行中ジョブ、EP-06 再送と EP-05 は 409 `lock_held`、EP-08 は 409 `lock_in_use`。EP-10 とロックは即時に見え、EP-02 の `last_crawl` と EP-09 は `running` が見えるまで数百ミリ秒かかることがある。`crawl_started_at` から削除判定の開始まで 0.4〜1.1 秒(終了通知の受理で削除ワーカーが起床するため、走査間隔 5 秒を待たない)。窓は見逃さなかった |
| AIT-21 | `force_delete`・`rewrite_mode` の中継 | passed | ttl 15 秒・割合しきい値 10%・`min_delete_count=0`、md 4 件のうち 2 件を削除。クロール B: `skipped_by_ratio`(`T=2`・`D=4`・`forced=false`・`reason=null`)、ジョブ `succeeded`・確認 `confirmed`、検索インデックスは 4 件のまま。クロール C(`force_delete=true`・`rewrite_mode=true`): `deleted`・`forced=true`・`deleted_count=2`・`rewrite_mode=true`。`loreley-deletions` の削除結果にも `forced`・`rewrite_mode` が複写される。テストは約 55 秒 |
| AIT-30 | EP-01 の全行照合(AAA-U-1) | passed | 2 回・1 回・0 回クロールした 3 ソースと、それまでの全ソースの全行で、`last_crawl`・`last_completed_at`・`document_count` 等が OpenSearch 直読みの独立計算と一致。2 回クロールしたソースの `last_crawl` は 2 回目(`top_hits` が最新を選ぶ)。`source_id` 昇順。test_30 の 3 テストで約 35 秒 |
| AIT-31 | EP-09・10 の絞り込み・並べ替え | passed | `sort=queued_at`/`-queued_at` の順序が逆転、`status` 絞り込み、範囲外の `page=2` は `items=[]`、`window_limit=10000`、古いジョブは `latest_for_source=false` |
| AIT-32 | EP-12 の `cat.*` | passed | `indices`・`shards`・`nodes`・`cluster` が `_cat/*`・`_cluster/health` の直読みと一致(`indices` の並びも独立実装と照合)。単一ノード |
| AIT-40 | 確認が必要な文書(EP-11) | passed | 31 ファイル(md 3・壊れた PDF 26・70,000 バイト 2)で `enumerated_count=31`・`created_count=29`・`oversize_count=2`・`error_count=26`・`skipped_count=0`、ジョブ `succeeded`。索引にあるのは 29 件で、上限超過 2 件は索引になく `loreley-jobs` の記録のみ。`tab_counts={skipped:0, extract_failed:26, oversize:2, summary_pending:0}`。`extract_failed` は 25 件 + 1 件で重複なし、`title` はファイル名。同一クロールの文書は `last_seen_at` が全件同一なので、同順位の `document_id` 昇順規則が効く状態で確認。test_40 の 2 テストで約 23 秒 |
| AIT-41 | `skipped` の `existence` | passed | 直接書いたスキップ記録 2 件が `existing`(実在文書)・`new`(存在しない ID)。`tab_counts.skipped=2`。既定の `-last_skipped_at` と `sort=last_skipped_at` の反転も確認。**Crawler が書いた記録との照合ではない**(AAPI-U-7 は未検証) |
| AIT-50 | 取消 | passed | `send_started_at` の観測から取消の受付(202)まで約 0.03 秒、取消後 `cancelled` まで約 1.1 秒。警告は `[{"code":"polling_aborted","confirmation":"unconfirmed"}]`、`deletion.confirmation=unconfirmed`、`registration` は `partial=false`・`phase=final`。打ち切った時点の `deletion.summary` は `status=running`・`observed_at` あり・`deleted_count` 等は null。窓は約 10 秒で、実行した 2 回とも見逃さなかった。test_50 の 2 テストで約 25 秒 |
| AIT-51 | 孤児ロックの解放 | passed | 孤児ロックの `lock.job` は `status=succeeded`・`job_type=crawl`・`trigger=manual` と `lease_expires_at`。EP-06 の 409 `details.existing_job` も同内容で `lock_state=orphan`。EP-08 は `released=true`・`failed_job_id=null`、再送は `released=false`。解放しても終端ジョブの `status` は変わらない。解放後の EP-06 は 202 → `succeeded`。孤児ロックは OpenSearch へ直接書いた(ロック文書の形式は、実 Crawler が実行中に書いたロック文書を直読みして合わせた) |
| AIT-60 | ソース削除 | passed | 実行待ちの間、削除対象 S の設定 `status` は `active` のまま(`deleting` は実行開始から。crawler-architecture 8.1 の順 0 と一致)。EP-02 `held_delete`、EP-06 は 409 `lock_held`(`existing_job.job_type=source_delete`)、EP-07 は 409 `job_not_cancellable`、EP-08 は 409 `lock_in_use`(計画の表にない確認を追加)。完了後 EP-10 `succeeded`、EP-02・11 は 404、EP-01 から消え、文書・記録なし、別ソース Z は残る。EP-08 は `released=false`(削除ジョブがロックを自分で消す)。S のジョブ記録は削除後も EP-10 で読める。約 33 秒 |
| AIT-90 | Crawler 停止 | passed | EP-13 の `crawler` が `abnormal`・`reason=name_not_resolved`(他は `normal`)。EP-03〜08 は 503 `crawler_unreachable`(`retryable=true`)。副作用なし(新規ソースは 404 のまま、既存ソースは `active` で文書 1 件、ロックなし)。EP-01・02・09・10・11・12・14 は 200。復旧後 EP-13 が `normal`、EP-06 が 202 → `succeeded`。約 35 秒 |
| AIT-91 | Indexer 停止 | passed | EP-13 の `indexer` が `abnormal`・`name_not_resolved`、読み取りの EP は 200。**クロール**: 受付 202 のあと `failed`・`failure_reason=indexer_unavailable`・`failure_detail="Indexer が応答しない(connection_error)"`、`rerunnable=true`・`rerun_blocked_reason=null`・`latest_for_source=true`、ロックは解放。**ソース削除**: `failed`・`indexer_unavailable`・`failure_detail="Indexer が応答しない(discard_deletions。connection_error)"`(順 1 の discard で失敗)。失敗後は EP-01・02 が `status=deleting`・`delete_job`、EP-04・06 は 409 `source_deleting`、同内容の EP-03 は 409 `source_already_exists`(`details={"status":"deleting"}`)、EP-11 は 200、文書 2 件は残る。**復旧後**: EP-05・EP-06 の再実行とも `succeeded`。削除したソースは EP-02・11 が 404、EP-01 から消え、文書・設定は 0。古い失敗ジョブは `latest_for_source=false`・`rerunnable=false`・`rerun_blocked_reason=superseded`。約 49 秒 |
| AIT-92 | OpenSearch 停止 | passed | EP-01・02・09・10・11・12 は 503 `unavailable`(`retryable=true`)。EP-13 は `opensearch=abnormal`(`name_not_resolved`)、`api`・`web` が `normal`、`crawler`・`indexer` も `normal`/`reason=null`(それぞれの `/healthz` が OpenSearch に依存しないため)。EP-14 と `/healthz` は 200。EP-06 は 503 `crawler_unavailable`(`retryable=true`。`crawler_unreachable` ではない)。復旧後、4 サービス(opensearch・indexer・crawler・api)が healthy、EP-01 200・EP-13 全 `normal`・クロール `succeeded`・文書 2 件。約 85 秒 |

障害系の途中失敗時の後始末(0008): AIT-92 の停止区間の中に一時的な `assert False` を入れて実行 → 1 failed のあと `finally` で 4 サービスが `running healthy` に戻り、EP-13 も全 `normal`(約 70 秒)。確認後にテストを元に戻した(退避コピーとの `diff` 一致)。許可リスト外(`stop api`・`stop opensearch-init`・`down crawler`・`stopped("api")`)は、docker を呼ぶ前に `ValueError` になることも確認した(0005・0008)。

### 4.4 0021 B 章(結合テストへの申し送り)の判定

申し送り元: `agent_tasks/20261123_implement_admin_api/0021-task-review-and-handoff.md` の B 章。**確認済み**=この IT で実機で見た、**一部確認**=一部だけ見た(見ていない部分を併記)、**未検証**=この IT では見ていない。

| B の項目 | 判定 | 根拠・備考 |
| --- | --- | --- |
| AAA-U-1 クエリの意味(並べ替えの順序・`terms` の `size`・`top_hits`) | **確認済み** | AIT-30(複数ソース・複数ジョブ。2 回クロールのソースで `top_hits` が最新を選ぶ。全行を独立計算と照合)、AIT-31(`sort` の順序逆転)、AIT-32(`cat.*`・`cluster.health`)。AIT-30 は、レビュー対応で、登録ソース総数を 12 件以上(クロールしないソースを追加)にし、`len(rows) > 10`(OpenSearch の `terms` 集計の既定 `size` 10 を超える)をアサートする形に強めた。その状態で 2 回連続で成功した。api は `terms` の `size` に取得対象のソース数を渡している(コードによる。`apps/api/.../queries.py`)ので、`size` が既定のままになる退行は検出できる。12 件を大きく超える規模(数百件)は未検証 |
| AAA-U-2 `mget`・`msearch` の実応答の形、`ids` クエリ、スレッド間共有 | **一部確認** | `ids` クエリは AIT-41(`existing`・`new`)で確認。`mget`・`msearch` は、これらを使う EP が実 OpenSearch に対して正しい値を返したことでの間接的な確認で、応答の形を見る専用のアサートはない。スレッド間共有の専用の確認はない(未検証) |
| AAA-U-3 `refresh_interval`・`max_result_window` | **一部確認** | 検索で読む EP の反映遅れは、**少なくとも 1 回の取りこぼし**(EP-03 直後の EP-01 でソースが見えない。P3a)を観測した。約 1 秒は設計の既定値(設計 AAA-P-6 が推測と明記)で、**最大遅延は未測定**、`refresh_interval` の設定値も読んでいない。`window_limit=10000` の応答と、範囲外ページ(`page=2`)が `items=[]` になることは確認。10,000 件を超える実データは未検証 |
| AAA-U-7 同時実行上限(16・4・8)の実測 | **未検証** | IT では並行リクエストの負荷をかけていない |
| AAA-U-10 期限後に残るスレッドの数と時間 | **未検証** | EP-13 の確認の期限後のスレッドは測っていない。AIT-90〜92 は、停止中の EP-13 の応答の値を確認しただけ |
| EP-07 実行中ジョブの取消 | **一部確認** | AIT-50: 実行待ちは 200 `cancelled`、実行中(終了通知の送信後)は 202 → `cancelled`・`cancel_after_finish_notice=true`・警告 `polling_aborted`。終端のジョブの再取消は 409 `job_already_finished`。AIT-60: 削除ジョブの取消は 409 `job_not_cancellable`。**終了通知の送信前の実行中取消**(`cancel_after_finish_notice=false`、登録途中は `partial=true`)は未検証(7 章) |
| EP-08 実ロックの解放 | **一部確認** | AIT-51: 孤児ロックの解放(`released=true`・`failed_job_id=null`)・再送 `released=false`・解放後のクロール成功は確認。ただし**解放したのは OpenSearch へ直接書いた孤児ロック**で、実行中ジョブのロックの解放(`failed_job_id` が非 null になる経路)は未検証(`lease_expired` と同じ。7 章) |
| EP-06 の `lock_held`・EP-08 の `lock_in_use`(409) | **確認済み** | AIT-20(実行中)・AIT-60(実行待ちの削除ジョブ)。EP-06 は `lock_held`(AIT-51 では `lock_state=orphan`)、EP-08 は `lock_in_use`。申し送りの「EP-06 の `lock_in_use`」は、この IT では EP-08 の `lock_in_use` として確認した(EP-06 が `lock_in_use` を返す経路は、計画・テストにない) |
| 実行中の `lock_state` | **一部確認** | `none`・`held_crawl`(AIT-20・50)・`held_delete`(AIT-60)・`orphan`(AIT-51)を実機で確認。`stalled=true`・`lease_expired` などは未検証(記録があるのは上記の値だけ。`lock_state` の全分岐は単体テストの範囲) |
| `force_delete=true`(EP-06) | **確認済み** | AIT-21: 割合ルールで止まった削除が `force_delete=true` で実行される(`forced=true`・`deleted_count=2`)。`rewrite_mode=true` も中継された |
| `force_delete=true`(EP-05) | **仕様上確認の対象外** | EP-05 は本文を取らず、`force_delete` は `null`(admin-api B 3.5)。強制削除は EP-06 で確認した。EP-05 はソース削除そのもの(AIT-60・91)で確認 |
| EP-12 の `relocating` の `node` 表記、複数ノード・複数シャードの `cat.*` | **一部確認** | 単一ノード・4 索引の `cat.*` の列を直読みと照合(AIT-32)。複数ノード・`relocating` は未検証 |
| AAPI-U-7 `skipped` 行の `existence`(`ids` の `_id` と `document_id` の一致) | **一部確認** | AIT-41: `existence` の `existing`・`new` の判定は確認。ただしスキップ記録は**直接書き込み**で、**実 Crawler が書いた記録**は 0 件のまま(取得の権限エラーを macOS の bind mount で確実に作れないため)。AIT-40 は、期待する `document_id` を独立実装(`compute_document_id`)で計算して EP-11 の項目と照合するが、これは `extract_failed` の文書であり、スキップ記録の `document_id` と検索インデックスの `_id` の一致の確認ではない |
| ページングの窓 10,000 の実データ | **未検証**(`window_limit=10000` の値のみ確認) | 10,000 件の文書・ジョブを作っていない |
| OpenSearch の部分失敗(一部シャード障害) | **未検証** | AIT-92 は OpenSearch 全体の停止(503 `unavailable`)のみ |
| `ClientDisconnect` の実機 | **未検証** | 単体テストのみ |
| BAPI-U-2 の残り(入れ子のマウント、`FastAPI(root_path=…)`) | **未検証** | compose で起動した実 api の `/api/admin/v1` 配下で全 EP が動作し、`/api/admin/v1/openapi.json` が 404 であることは確認したが、入れ子のマウント・`root_path` は試していない |
| AAM-U-7 の後半(E の型生成の手順との整合) | **対象外** | フロントエンドのタスク(FARC)の事項 |

### 4.5 実行スクリプト・後始末の確認

| 項目 | 結果 |
| --- | --- |
| 成功経路 | 4.1 のとおり。終了後にコンテナ・ボリューム・ネットワーク・`data/` が残らない |
| 事前確認の中止(P2) | `data/` に空でないファイルを置くと、何も消さず終了コード 1、コンテナ・ボリュームは作られない(確認後にファイルを削除) |
| 障害系の途中失敗 | 4.3 の末尾のとおり。`finally` で復旧し、後始末まで終わる |
| 他プロジェクトへの影響 | P4 の前後で `docker ps -a` の出力が一致(他プロジェクトの `opensearch-opensearch-1`(停止中)のみ。操作していない) |
| compose v2.3.3 の `stop`/`start`(P4 冒頭) | `stop crawler`/`indexer`/`opensearch` は対象の 1 つだけが止まり、他は Up のまま・コンテナ ID も不変。OpenSearch 停止中も crawler・indexer は healthy のまま。`start opensearch` から 4 サービスが healthy になるまで約 56 秒 |
| 静的検査 | `ruff check`・`ruff format --check`(11 files)・`uv lock --check`・`pytest --collect-only`(23 件)・`bash -n`: OK(レビュー対応後の最終版で再実行して確認した)。**`shellcheck` は未インストールのため未実施** |

実機で動かしていない経路: 事前確認のうち、`loreley-it` の残りのコンテナ・ボリュームを検出して中止する経路、ポート使用中の中止(`describe_port_owner`)、`compose down` 失敗時の分岐、シグナル(INT・TERM)、`--keep`、待機の上限超過(終了コード 10)。

### 4.6 最終確認(P5)

2026-11-25 に、P4 完了後のコードに対して次を実施した(api IT はいずれも `--keep` なしで、`down -v` 済みのクリーンな状態から。スクリプトの事前確認は、`loreley-it` の残りを検出すると中止するので、各実行は残りがない状態で始まっている)。所要時間は、`tests/integration/api/results/` のログ末尾の値(`.gitignore` 済みで、手元にだけある)。

**api IT の全件実行(23 件)の履歴**

| 実行 | 結果 | 備考 |
| --- | --- | --- |
| 1 回目(P5) | 23 passed(334.0 秒) | |
| 2 回目(P5) | 22 passed・1 failed(AIT-60)。pytest 318.78 秒 | `lock_lost`(`lease_expired`)。実行中にホストがスリープしたと**推定**(記録なし。下記) |
| 3 回目(`caffeinate -i` 付き) | 23 passed(339.7 秒) | |
| 4 回目(`caffeinate -i` 付き) | 22 passed・1 failed(AIT-20)。pytest 337.33 秒 | テストの待ち不足(下記)。修正した |
| 5 回目(修正後・`caffeinate -i` 付き) | 23 passed(354.1 秒) | |
| 6 回目(修正後・`caffeinate -i` 付き) | 23 passed(357.8 秒) | |
| 7 回目(レビュー対応後・`caffeinate -i` 付き) | 23 passed(pytest 380.75 秒、スクリプト全体 482 秒) | レビュー指摘への対応後(下記) |
| 8 回目(同上) | 23 passed(pytest 375.41 秒、スクリプト全体 466 秒) | |

AIT-20 の修正後のコードで、クリーンな状態から 2 回連続で全 23 件が成功した(5・6 回目)。1・3 回目も修正前のコードで成功している。

**レビュー対応(7・8 回目)**: code-reviewer・test-reviewer・document-reviewer の指摘への対応でテストを強めた(AIT-20: 409 再送のオプションが走行中ジョブに適用されないことをジョブ側で確認、窓の確認順の入れ替え、終了直後の `latest_for_source`・`rerunnable` の待ち / AIT-30: 登録ソース 12 件以上 / AIT-40: `external_id` と `document_id` の対応 / AIT-60: 削除後も過去のクロールのジョブが EP-10 で読めることと、ジョブ記録が残ること / AIT-91: `failure_reason=indexer_unavailable` の断定と、EP-10・11 などの読み取りの追加 / 反映遅れの待ちの追加)。対応後のコードで、クリーンな状態から 2 回連続で全 23 件が成功した(7・8 回目。スリープによる遅延はなし)。あわせて Crawler IT スクリプトを変更した(新しい共通変数 2 つの固定)ので Crawler IT を 1 回再実行し、14 passed(38.9 秒、スクリプト全体 137 秒)だった。終了後、`loreley-it` のコンテナ・ボリューム・ネットワークと `data/` は残っておらず、他プロジェクトのコンテナ(`opensearch-opensearch-1`。停止中)は変わっていない(実装担当と私の両方が確認)

- **2 回目の失敗(AIT-60)は、実行中のホストのスリープによると推定している(スリープの記録はない)**。AIT-60 の別ソースのクロールが `failure_reason=lock_lost`・`failure_detail=ロックの所有権を失った(lease_expired)` で失敗した(失敗メッセージはログに残っている)。推定の根拠は、pytest の経過が 318.78 秒なのに、実行全体の壁時計が約 1 時間 42 分で、Crawler のコンテナのログが約 1 時間 38 分途切れていたこと(いずれも実行時の観察。作業記録 0009 に書いてあるのは Crawler のログの途切れだけ)。Crawler のログの実物は後始末(`down -v`)で消えており、再確認できない。ログファイル名の時刻(この実行は 14:56:00 開始、次の実行は 16:40:48 開始)は、約 1 時間 42 分と矛盾しない。この間にホスト(とコンテナ)が止まり、ロックのリースが切れたと考えられる。ほかの原因(Docker VM の停止など)を切り分けた記録はない。同じ実行の他の 22 件は成功した。以降は `caffeinate -i` を付けて実行した(3〜6 回目は `lock_lost` が出ていない)。**IT の実行中はホストをスリープさせないこと**(README に記載)
- **4 回目の失敗(AIT-20)は、テストの待ち不足と判断した**。ログの失敗メッセージは「`last_completed_at` がジョブの `finished_at` と一致しない(値は `None`)」。EP-02 の `last_crawl` は `succeeded` になっていたが、`last_completed_at` がまだ `null` だった(0009)。最終クロール・最終完了時刻・文書数は別々に検索で読まれるため、設計 AAA-P-6 の反映遅れで、どれか 1 つが遅れたと判断した(別の原因の切り分けはしていない。約 1 秒は設計の推測で、最大遅延は未測定)。アプリの不具合ではない。待ちの条件に `last_completed_at`(ジョブの `finished_at` との一致)と文書数を加えた(`test_20_crawl.py`。EP-02 と EP-01 の両方)。アサートの期待値は変えていない。**確認する値は、読む EP ごとに待ち条件に含める**方針で、この失敗は、その条件の不足だった

**`apps/api` の単体テスト・ruff(退行確認)**: `uv run pytest -q` が 3423 passed、`ruff check` が All checks passed(0009)。`apps/` は本タスクで変更していない。所要時間は記録がない

**既存 IT の再実行(`compose.yaml` を変更したため)**: `scripts/run-crawler-integration-test.sh` が 14 passed(35.13 秒)、`scripts/run-indexer-integration-test.sh` が 40 passed(16.60 秒)。出所: `tests/integration/crawler/results/pytest-20261125-144535.log`・`tests/integration/indexer/results/pytest-20261125-144729.log`(passed 件数と所要時間はログの値)

**他プロジェクトへの影響**: P5 の `docker ps -a` による前後確認は、記録がないため書かない(P2〜P4 の確認は 4.1 と 0005〜0008)

## 5. 評価・発見事項

1. **設計との食い違いはなかった**。P2〜P4 のすべてのシナリオで、実機の応答は設計(admin-api-v0.1、crawler-architecture-v0.4 など)と一致した。テストを実機に合わせて曲げた箇所はない。`apps/`(api・crawler・indexer)は変更していない(アプリの不具合は見つからなかった)。
2. **設計が値を定めていない(複数の値を許す)箇所の観測値**。食い違いではなく、実測値として記録する。
   - EP-13 の `reason`: 停止した crawler・indexer・opensearch はすべて `abnormal`・`name_not_resolved`。api がコンテナ内から動くため、停止したコンテナの名前を引けない。設計が許すもう一方の `connection_refused` は出なかった(計画段階で、ホスト上の手動スモーク(0018)とは値が違う可能性を想定していた)
   - EP-06 の OpenSearch 停止中の 503: `crawler_unavailable`(`crawler_unreachable` ではない)
   - OpenSearch 停止中の EP-13: `crawler`・`indexer` は `normal`(`/healthz` が OpenSearch に依存しないため)
   - `skipped_by_ratio` のとき `deletion.summary.deleted_count` は `null`(0 ではない。`deleted` で 0 件のときは 0)。設計 9.3 は値を定めていない
   - 実 Crawler が検出した原本サイズ超過の記録(`detected_by=crawler`)の `size` は `null`。EP-11 も `size: null`(設計 3.3.4「分かる場合だけ」と整合)。`size_hint` が付く場面は未確認
   - 取消の打ち切り時点の `deletion.summary` は `status=running`・`observed_at` あり・`deleted_count` 等は `null`
3. **検索で読む EP は、反映が遅れることがある**(EP-01・09・11、EP-02 の最終クロール・最終完了時刻(`last_completed_at`)・文書数)。設計 AAA-P-6 は最大約 1 秒と推測しているが、**この IT で見たのは、少なくとも 1 回の取りこぼし**(P3a。EP-03 直後の EP-01 でソースが見えない)と、P5 の AIT-20 の失敗(4.6。EP-02 の `last_completed_at` が `null` のまま)で、**最大遅延は測っておらず、`refresh_interval` の設定値も読んでいない**。ID 指定で読む EP-10 のジョブ本体とロックは即時。Admin API は `refresh` を呼ばない設計なので、利用側は次の取得で追いつく。**待ちの方針**: 確認する値は、読む EP ごとに待ち条件に含める。AIT-20 の不安定さ(4.6)は、この条件の不足(`last_completed_at` と文書数を待ち条件に入れていなかった)だった。レビュー後は、EP-10 の `latest_for_source`・`rerunnable` や EP-02 の `delete_job` など、同種の箇所も待ち条件に含めた(テストのコメントでは、これらも検索の結果から導く値とされている)
4. **窓の実測**: Crawler のポーリング間隔 10 秒・Indexer の走査間隔 5 秒の設定で、ロックを持つ窓は約 10 秒。AIT-20・50・60 は窓を見逃さなかった(各 2 回の実行)。`crawl_started_at` から削除判定の開始まで 0.4〜1.1 秒
5. **Indexer 不達時の Crawler の失敗は速い**(リトライ 3 回・バックオフ 1・2 秒)。クロール・ソース削除とも数秒で `failed`(`indexer_unavailable`)になり、ポーリング上限 120 秒には達しなかった。停止中に始めたクロールは `failed`・`rerunnable=true` で、復旧後の再実行で完了する
6. **`start crawler`・`start indexer` は、依存の使い捨て `opensearch-init` を同じコンテナで再実行する**(compose v2.3.3。冪等で害なし)
7. **AIT-21 の条件を計画から変更した**: 計画は ttl 1 秒だったが、ttl 1 秒では更新した文書も判定までに期限切れになり、強制削除の削除件数が 4 になって成立しない。ttl 15 秒・割合しきい値 10%・`min_delete_count=0`(T=2、D=4、T÷D=50% > 10%)に変更した(indexer-architecture 9.2・9.3・9.7)。期限切れは実時間で作る(直接書き込みはしない)
8. **AIT-91 のソース削除は、実行待ちではなく失敗後の状態で `deleting` 系を確認した**(安定して確認できるため)。AIT-60 に、計画の表にない EP-08 の 409 `lock_in_use` の確認を追加した
9. `./run-api-integration-test.sh --help` をスクリプトのディレクトリ内から実行すると `usage()` が失敗する(既存の Crawler 用スクリプトと同じ。リポジトリのルートからは動く。通常の利用に影響がないので修正していない)

## 6. 所要時間

| 項目 | 値 |
| --- | --- |
| 全 23 件(初回ビルドなし) | pytest 334〜381 秒(P4 とその後の成功 8 回: 344.8・342.8・334.0・339.7・354.1・357.8・380.8・375.4 秒。7・8 回目はレビュー対応で確認を増やした後の値)。失敗した 2 回は 318.78 秒(2 回目。スリープと推定される失敗で、壁時計とは大きく食い違う。4.6)と 337.33 秒(4 回目)。スクリプト全体は、P4 で 6 分 58 秒(起動・待機・後始末を含む。pytest との差は約 73〜75 秒。内訳は測っていない)。7・8 回目のスクリプト全体は 482 秒・466 秒(約 8 分)。P5 の 1〜6 回目のスクリプト全体の時間は記録がない |
| 初回(ビルドあり) | AIT-01 のみで、スクリプト全体約 4〜5 分(P2。イメージのビルドを含む) |
| 20 件(障害系なし) | pytest 約 172 秒 |
| 主なテスト | AIT-21 約 55 秒、test_30 約 35 秒(3 テスト)、test_40 約 23 秒(2 テスト)、test_50 約 25 秒(2 テスト)、AIT-60 約 33 秒、AIT-90 約 35 秒、AIT-91 約 49 秒、AIT-92 約 85 秒 |

計画段階の見込み(10〜20 分)より短かった。クロール 1 回は約 10〜12 秒(Crawler のポーリング間隔 10 秒による)。

## 7. 未検証事項

**項目別の判定は 4.4**。ここは、この IT が確認していないものの一覧。

- **EP-09 の複数ページ**: 26 件以上のジョブが必要で作っていない。ページングの実応答は EP-11(AIT-40。`extract_failed` の 25 件 + 1 件)で確認したのみ
- **AAPI-U-7**: 実 Crawler が書いたスキップ記録の `existence`(AIT-41 は直接書き込み)
- **`summary_pending`**: 空の確認のみ(`tab_counts.summary_pending=0`。LLM 要約の実装後。AAPI-U-8)
- **`size_hint`**: 原本サイズ超過記録に `size_hint` が付く経路(実 Crawler の検出では `size` が `null`)
- **AAA-U-7**(同時実行上限の実測)・**AAA-U-10**(期限後に残るスレッド)
- **10,000 件の窓**(`window_limit=10000` の応答値と範囲外ページのみ)、**一部シャード障害**(部分失敗)、**複数ノードの `cat.*`・`relocating`**
- **`ClientDisconnect`**、**入れ子のマウント・`root_path`**(BAPI-U-2)
- **`stalled=true`・`lease_expired`**: 実行中ジョブの期限切れロックと、その解放(`failed_job_id` が非 null)
- **EP-05 の `force_delete`**: 仕様上 `null` で本文を取らない。強制削除は EP-06 で確認した(4.4)
- **EP-07 の、終了通知の送信前の実行中取消**(`cancel_after_finish_notice=false`。登録途中は `partial=true`): AIT-50 は、実行待ちの取消と、終了通知の送信後の実行中の取消だけ
- **ソース削除でのスキップ記録の削除**(crawler-architecture 8.1): AIT-60 の対象ソースにはスキップ記録がない(実 Crawler にスキップを起こさせられない。AIT-41 と同じ理由)。文書・原本サイズ超過記録・削除記録・設定の削除と、ジョブ記録が残ることは確認した
- **`--keep` でスタックを残したままの pytest の繰り返し**: テストが作るソースは削除されず積み上がり、`support.py` の `OpenSearchProbe` のソース全件読み(上限 100 件)に達すると失敗しうる。繰り返すときは、100 件に達する前にスタックを作り直す(README に記載。この上限に達した実行はない。推測)
- `terms` の `size` の上限を超えるソース数、`mget`・`msearch` の応答の形の専用の確認、スレッド間共有(AAA-U-2)、`max_result_window` の設定値そのもの(AAA-U-3)
- 起動直後に Crawler が回復中(最大約 3 分。HO-45)の間の api の見え方(IT は全サービスが healthy になるのを待ってから始める)。`web` の成果物を mount しないときの EP-13(`deploy/compose/README.md` の「`web` が `abnormal` に見える」注記は、コードの読解による。実機は未確認のまま)
- `OPENAPI_ENABLED=true` のときの動作、認証・CSRF(スコープ外)
- 受付途中の猶予(`LORELEY_ADMITTING_LOCK_GRACE_SECONDS`)の Crawler と api での実効の一致(HO-44。`docker compose config` で同じ変数から渡ることは確認済み。ずれたときの表示と操作の食い違いは IT で確認していない)
- `shellcheck`(未導入)、Linux ホスト・他の OS・OpenSearch 3.9.0 以外のバージョン、Docker のバージョン・メモリ使用量の測定
- CI への組み込み(スコープ外)

### 不確実点(テストが依存している前提)

- **窓に依存**する(Crawler のポーリング間隔 10 秒・Indexer の走査間隔 5 秒)。極端に遅い・速い環境では AIT-20・50・60 が失敗しうる(失敗メッセージで原因は分かる)
- **OpenSearch への直接書き込み**(AIT-41・51)が Crawler の記録の形式に依存する。形式が変わるとテストが壊れて検出できる
- 検索の反映遅れ(約 1 秒は設計の推測で、最大遅延は未測定)を、上限 10 秒のポーリングで吸収している
- ホストと Docker VM の時計: AIT-21 は api の `Date` ヘッダを基準にしてずれを避けているが、AIT-51 の孤児ロックの `acquired_at`(2 時間前)は余裕が大きい

## 8. 再実行の手順

詳細は `tests/integration/api/README.md`。最小のコマンド(リポジトリのルートで。uv と Docker が必要):

```sh
scripts/run-api-integration-test.sh                 # 起動 → pytest → 後始末まで一括(約 7 分)
scripts/run-api-integration-test.sh --keep -k test_30   # 反復用。終了後もスタックと data/ を残す
```

- Crawler・Indexer の結合テストと同じプロジェクト名(`loreley-it`)・ポートを使うため、**同時には実行できない**。使用中のポートや前回の残りがあると、何も消さず中止する
- 結果は `tests/integration/api/results/pytest-YYYYMMDD-HHMMSS.log`(`.gitignore` 済み)にも残る。障害系の実測値は `[observed]` で出力される
- 再実行の結果は、上書きせず、この文書に新しい行・節として追記する

## 9. 申し送り

- **設計書の追従改訂(別タスク。ユーザー判断)**: `api-base-design-v0.1.md` 9.2 の次の項目の状態を更新する。本タスクでは設計書を変更していない。
  - HO-34(compose への `api` の追加)・HO-35(環境変数・索引名の配線。検索エイリアスに実体名を渡さない): `deploy/compose/compose.yaml` に実装し、実機で起動・動作を確認した(AIT-01 ほか)
  - HO-43(cron のタイムゾーンの共通変数): 実装し、AIT-01 の EP-14 `cron_timezone=Asia/Tokyo` で Crawler と同じ変数から api に届くことを確認した(Crawler の側の実効は、`docker compose config` での展開の確認)
  - HO-44(受付途中の猶予の共通変数): 実装し、`docker compose config` で Crawler・api に同じ変数から渡ることを確認した(ずれたときの食い違いは未検証。7 章)
  - HO-40・41(認証なし・ブラウザ経由の書き込みへの保護なしの注意書き): `deploy/compose/README.md` に追記した(P1)。IT での確認の対象ではない。HO-40 の文言(「`:ro` のマウントだけ」)を、`deploy/compose/README.md` の記述(Crawler の `:ro` の mount と、コンテナ内で読める範囲。FileSystem Connector の `root` はコンテナ内の任意の絶対パスを受け付ける。コードからの推測で実行は未確認)に合わせて直す
  - HO-45(起動直後の見え方): `deploy/compose/README.md` に、設計書の記述(実機未確認)と実機確認したことを分けて記載済み(P1 とレビュー対応)。**実機で確認したのは、Crawler・Indexer の停止中も読み取りの EP が OpenSearch だけで応答すること**(AIT-90・91)。**起動直後の見え方(回復中の接続拒否など)は未検証**(IT は全サービスの healthy を待ってから始める。7 章)
- **据え置き**: `apps/api/Dockerfile` の冒頭近くの古いコメント(「現時点の `api` は基盤だけで、Web UI の配信(`/app/web`)は含めない。」)。HO-36(Web の成果物)で Dockerfile に触るときに直す(0021 C)。本タスクでは Dockerfile に触れていない
- **スクリプトの重複**: Indexer・Crawler・api の 3 つの実行スクリプトが重複している(共通化は未対応。Crawler の IT の記録の負債と同じ)

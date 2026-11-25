# 0006 P3a: ソース管理とクロールの IT(AIT-10・11・12・20・21)

日付: 2026-11-25
担当: code-implementer(実装)、メインエージェント(静的検査・残骸の再確認)

## 実施内容

- `tests/integration/api/test_10_sources.py`(AIT-10・11・12)と `test_20_crawl.py`(AIT-20・21)を追加(`support.py` に待ちヘルパを追加のみ、`conftest.py` 変更なし)
  - AIT-10: EP-03 登録(201、`loreley-sources` 直読みで `ttl`(秒)・`ratio_threshold`(割合)に変換保存)、同内容再送 200、内容違い 409、EP-02 初期状態、EP-04 更新、EP-01 昇順
  - AIT-11: 実 Connector の違反(相対 `root`・未知項目)の 400 `config_invalid`(EP-03・04。保存されない)
  - AIT-12: 未登録ソースの EP-02・11・04・05・06 の 404 と EP-08 の `released=false`
  - AIT-20: 起動 → `running` 観測 → 実行中に EP-02 `held_crawl`、EP-09 `active`、EP-06 再送 409 `lock_held`、EP-05 409 `lock_held`、EP-08 409 `lock_in_use` → 終了後の EP-10・02・01
  - AIT-21: `force_delete=true`・`rewrite_mode=true` の中継(A → 2 件削除 → B(`skipped_by_ratio`)→ C(強制削除))
- `support.py` 追加: `run_crawl`、`wait_until_expired`、`AdminApi.server_now`、`wait_for_source_listing`、`wait_for_source_detail`、定数 `READ_LAG_*`・`EXPIRY_*`

## 変更したファイル

`tests/integration/api/support.py`(追加)、`test_10_sources.py`・`test_20_crawl.py`(新規)。`apps/` は変更なし。

## 判断・設計上の理由(プランからの変更)

- **AIT-21 の条件をプランの「ttl 1 秒」から変更**(プラン 13 章の未解決事項の確定): ttl 1 秒では更新した文書も判定までに期限切れになり強制削除の `deleted_count` が 4 になって成立しない。`ttl_seconds=15`・`ratio_threshold_percent=10`・`min_delete_count=0`、md 4 件のうち 2 件を消す(T=2、D=4、T÷D=50% > 10%)で、通常クロール B は必ず `skipped_by_ratio`、強制削除の C は `forced` で 2 件削除(indexer-architecture 9.2・9.3・9.7)。期限切れは直接書き込みでなく実時間で作る(A の `last_seen_at` から TTL+2 秒を `wait_until_expired` でポーリング。現在時刻は api `/healthz` の `Date` を使い、ホスト時計のずれを避ける)。テストは約 55 秒
- **検索で読む EP は反映が最大約 1 秒遅れる**(設計 AAA-P-6 に既出): EP-03 直後の EP-01 でソースが見えず初回に 1 件失敗。EP-01・09、EP-02 の最終クロール・文書数は、期待状態になるまで上限付き(10 秒、0.3 秒間隔)でポーリングしてから確認。アサートの値は変えていない。ID 指定で読む EP-10 とロックは即時
- `schedule_cron` は `"0 3 29 2 *"` を使い、IT のソースが定期起動されて他テストの窓を乱すのを避ける

## 検証結果

- ruff check・format、`pytest --collect-only`(12 件): OK(メインエージェントも再実行)
- クリーンな状態から `scripts/run-api-integration-test.sh`(`--keep` なし)で全件実行: 12 件成功(終了コード 0、pytest 56 秒)。途中の `--keep` 反復で初回 1 件失敗(上記の反映遅れ。テスト側の待ち不足)を修正して解消
- 終了後: `loreley-it` のコンテナ・ボリューム・ネットワーク・`data/` なし、ポート空き、`docker ps -a` は他プロジェクトの `opensearch-opensearch-1` のみ(メインエージェントが再確認)
- `apps/` 変更なしのため単体テスト・ruff は未実施。shellcheck は未実施のまま

## 発見事項(実機の観測値。設計との食い違いはなし)

- `skipped_by_ratio` のとき `deletion.summary.deleted_count` は `null`(0 ではない。`deleted` で 0 件のときは 0)。設計 9.3 は値を定めておらず食い違いとは扱わない。テストは検索インデックスの件数 4 と `not deleted_count` で「削除なし」を確認
- B: T=2、D=4、`forced=false`、`reason=null`、ジョブ `succeeded`、確認状態 `confirmed`。C: `deleted`・`forced=true`・`deleted_count=2`・`rewrite_mode=true`。`loreley-deletions` の削除結果にも `forced`・`rewrite_mode` が複写
- 実行中の窓で、EP-10 とロックは即時、EP-02 の `last_crawl` と EP-09 は `running` が見えるまで数百ミリ秒かかることがある。`crawl_started_at` から削除判定開始まで 0.4〜1.1 秒(終了通知の受理で削除ワーカーが起床するため走査間隔 5 秒を待たない)
- AIT-11 の固定文: 相対 `root` は field=`connector_config.root`・detail「`/` で始まる絶対パスでない」、未知項目は field=`connector_config`・detail「未知の項目がある」(設計 2.5 の分解どおり)
- EP-03 は `ttl_days=2`・`ratio_threshold_percent=12.5` を `ttl=172800`・`ratio_threshold=0.125` で保存。更新後(3600 秒・20%)は `ttl_days=null`

## 未対応事項・次にやること

- P3b(AIT-30・31・32・40・41・50・51・60)。AIT-30 用に `OpenSearchProbe` へ `terms`・`top_hits` 直読み、AIT-41・51 用に OpenSearch 直接書き込みを実装する。EP-09・11 は `poll_until` で反映待ちが要る
- 結果文書(P5)に、EP-01・09 などの検索系 EP の反映遅れ(最大約 1 秒。設計 AAA-P-6)を観測事項として記録する

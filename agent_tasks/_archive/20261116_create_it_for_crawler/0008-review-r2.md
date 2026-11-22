# 0008 レビュー R2(フェーズ 3〜5)

日付: 2026-11-16
レビュアー: code-reviewer(スクリプト・support・コード面)、test-reviewer(網羅性・品質・再現性)。実装担当(code-implementer)とは別。
対象: `scripts/run-crawler-integration-test.sh`、`tests/integration/crawler/**`(`.venv`・`results`・`data` を除く)、`.gitignore`(比較基準: 基準コミット `6970478`、未コミット差分)

## 結果

両レビュアーとも **Critical / Important なし**。次工程(フェーズ 6)に進めてよい。0001 の 11 項目はすべてテストで検証されており、0001 の対象外には踏み込んでいない。`apps/crawler` に変更なし、`bash -n`・`ruff check`・`ruff format --check` は通過。

### 0001 のテスト範囲 11 項目の対応(test-reviewer)

| # | 項目 | テスト |
| --- | --- | --- |
| 1 | Crawler が healthy | `test_01`(3 件) |
| 2 | `POST /sources` 登録 | `test_10` 登録(201・再送 200・`loreley-sources` を直接確認) |
| 3 | クロール起動 | `test_20`〜`test_50` |
| 4 | FS 列挙・取得 | `test_20` 主要フロー(5 件、対象外は索引されない) |
| 5 | 索引・ジョブ記録の直接確認 | 同上 |
| 6 | 実 Indexer との件数照合 | `test_20`(5==5+0、2==1+1)、`test_30`(4==4+0) |
| 7 | TTL 削除 | `test_30` |
| 8 | ソース削除ジョブ | `test_40` |
| 9 | サイズ超過 1 件 | `test_20` |
| 10 | ロックの実体と解放 | `test_20` ロック、`test_40` |
| 11 | メンテナンスフラグ 409 | `test_50` |

偽陽性の確認(test-reviewer): 件数照合は Indexer が自分で数えた値との突き合わせで具体値を固定、`document_id` はテスト側独立実装との集合一致、TTL の「残る文書」は last-seen が更新されないと `validation_failed`/`target_count` で落ちる、メンテナンスフラグを無視すれば 202 になって落ちる。`compute_document_id` は Indexer の実装と一致(code-reviewer が確認)。

## 指摘と対応

| 指摘 | 内容 | 対応 |
| --- | --- | --- |
| code S1 | `compose down` が失敗しても `data/` を消す | **対応**(`down` 失敗時は `rm` を飛ばして手動削除を案内) |
| code S2 / test N4 | `data/` を umask 任せで作る(077 だと uid 10001 が読めない) | **対応**(`mkdir -p` 後に `chmod 755`) |
| code S3 | `describe_port_owner` が相手を特定できないとき何も出さない | **対応**(「特定できませんでした」を出す) |
| code S4 | `force_last_seen_at` が 100 件超で黙って打ち切る | **対応**(上限に達したら assert。`_update_by_query` への変更はしない) |
| code N(クォート) | 後始末コマンド表示のパスが未クォート | **対応** |
| code N(SIGTERM) | `kill` でスクリプト本体だけに届くと、前景の子が終わるまで cleanup されない | **対応しない**(Indexer 用スクリプトと同じ既存の性質。端末の Ctrl-C は問題なし) |
| code N(追加テストの ID) / test S1 | 追加テストに ID が無い。名前は「サイズ超過でなくなった」だが実際はファイル削除 | **対応**(`..._when_the_file_is_removed` に改名、`CIT-23` を付与)。「上書き」変種(arch 6.4 の (a))は**追加しない**(要件外)。追加テスト自体は残す(CIT-20 では整理が空走査になるため。結果記録に「プランにない追加テスト」と明記する) |
| test S2 | TTL テストで設定の受け渡し(`ttl`・`ratio_threshold`・`min_delete_count`)と B の `registration` を確認していない | **対応**(`loreley-deletions` の結果と B の `registration` の `created=1`・`updated=1` を追加) |
| test S3 | ロック観測の窓(約 3.3 秒)とホスト時計との比較(`lease_expires_at` の判定) | 窓の変更は**対応しない**(実測で十分、失敗メッセージで原因が分かる)。`now + 1h` の 1 時間にコメントを付ける。残る依存は結果記録の「未対応・不確実点」に書く |
| test S4 | メンテナンスフラグを `enabled:false` で下ろす手順が未検証 | **対応しない**(0001 の範囲外)。結果記録に「未実施」と書く |
| test N1 | `"warnings" not in job` | **対応**(`not job.get("warnings")`) |
| test N2 | `kept2` の旧・新本文の長さが違う | **対応しない**(無害) |
| test N3 | サイズ超過テストが `compose.test.yaml` の値に依存 | **対応**(失敗メッセージ・コメントに前提を一言) |

反映は code-implementer が実施中。Critical / Important がないため、再レビューは行わず、メインが最終コードを実機で検証する(フェーズ 6 の一括スクリプト 2 回連続)。

## 結果記録(フェーズ 6)に書く事項(R2 から)

- 未実施: `fetch_permission_denied` / `skip` 記録 / `partially_succeeded`、ソース削除の順 3 の `skip` 記録の削除、ソース削除ジョブ起動時のメンテナンス 409(README 6 章に記載があるが未検証)、メンテナンスフラグを `enabled:false` で下ろす手順
- 実機未確認: `check_no_leftover_stack` の失敗経路、コンテナがポートを占有している場合の `describe_port_owner`、`shellcheck`
- 不確実点: ロック観測の窓への依存、ホストと VM の時計差(`lease_expires_at` の判定)、TTL の前提作りが Indexer 内部の項目名 `last_seen_at` に依存

## 次にやること

1. 反映結果(実機での 13 passed、終了コード 0)をメインが確認して作業記録 0009 に残す
2. フェーズ 6

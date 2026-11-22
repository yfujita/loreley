# 0046 SD v0.7 のレビューと指摘反映

## 概要
プラン 0041 のフェーズ5。document-reviewer が SD v0.7 をレビューした(総評: 軽微な修正で可。ただし Critical と Important の修正は必要。v0.2〜v0.6 の履歴は無傷、`interrupted` は状態として残っていない、§11.12 の ID 列挙の機械的突合は問題なし)。指摘を document-writer が SD v0.7 と PD v0.13 に反映した。

## 指摘と対応
| 重要度 | 指摘 | 対応 |
|---|---|---|
| Critical | 終了通知の「受理時の世代判定」と「再送は冪等」が矛盾し、受理済みの旧削除が `discarded`(`stale`) になりうる | 受理時の分岐の先頭に「`finish_received_at` が記録済みの再送は世代を見ず冪等(内容が異なれば409)」を置いた。`discarded`(`stale`) は `finish_received_at` の無い `running` に限定。判定表・競合表・D-11 を整合。D-39 追加 |
| Important | ソース削除の停止信号を `deletion-{source_id}` の存在確認にしたのは不適切(再登録、`loreley-deletions` 喪失、判定中の結果の上書き) | v0.6 の順序に戻した(非終端の削除結果を `discarded`(`source_deleted`) にしてから記録を削除)。削除側はバッチ前と各状態遷移の書き込み前に自分の結果を読み、終端なら止まる。書き込みは `if_seq_no` の条件付き更新。手順は「案」のまま |
| Important | 「先行する削除結果」の定義が無い | 同じ `source_id` で `finish_received_at` が自分より前(同値は `crawl_id` の辞書順)かつ非終端。`finish_received_at` の無い `running` は先行にならない(案)。§12.3・§12.5 更新 |
| Important | 保持件数Nの整理が待ち行列を壊しうる | 整理の対象は終端状態の結果のみ。`running`(待機中を含む)は数えず消さない。D-45 追加 |
| Important | 開始通知の `superseded` 化と終了通知の受理の競合 | 開始通知・終了通知の受理をソースごとに直列処理(代案: 条件付き更新)。案。D-40 追加 |
| Important | 試験が§3.9の分岐を覆い切っていない | D-39〜D-46 を追加(再送、`superseded` 化の対象と競合、判定中のソース削除、ソース削除で先行だけが `discarded` になった場合、`outcome=failed` が先行を待たない、`delete_error`、保持件数の整理、先行の定義)。§11.8・§11.12 を更新 |
| Suggestion | 3世代の例の前提/待機時間がポーリング上限を消費 | 前提(ロック解放後)を明記。受容事項(8)と §12.5 に追記 |
| Suggestion | 受理済み・待機中の結果が現行世代でなくなっても削除してよい根拠 | §3.9 項目7に明記(TTL再確認、対象は順番が来た時点で再抽出、設定スナップショットは当該世代の複写) |
| Suggestion | §4.5 の旧仕様の言い回し、`discarded` の説明 | 書き直し(世代の判定は受理時の1回、フラグは判定の前とバッチごと。`superseded` は `finish_received_at` の無いものに限る) |
| Nitpick | `forced` と `force_delete` の重複、D-19・D-33 の文言、Status API の `reason` | 反映 |

PD v0.13 の小修正:
- 9.2 #9 を「SD v0.7の範囲外。別の改版で扱う」に直した。
- 8行の「(作成予定。現行はv0.6)」を外した。40行と237行は「SD v0.7で反映済み」に書き直した。

## 変更したファイル
- `docs/v0.x/system-design/system-design-v0.7.md`
- `docs/v0.x/product-design/product-design-v0.13.md`

## 判断・留意点
- D-42(ソース削除で `discarded` になった先行の後ろの後続が進む)は、ソース削除が後続も同時に `discarded` にするため、依頼文のままでは成立しない。「後続は自分の結果を読んで止まる。先行だけが `discarded` になった場合に限り後続が進みうる」趣旨の試験にした。
- 依頼にない追記: 冒頭の「v0.6からの変更点」と改訂履歴に D-31〜D-46 と「レビュー反映」の1項目を追加した。
- 追加した規則(直列処理の方式、先行の定義、`if_seq_no`、`waiting_for`)はすべて「案」。

## 未対応事項
- `failed` の理由コードのうち `outcome_failed`・`outcome_cancelled` は「削除を行わなかった」場合を含む(v0.6 でも `failed`)。PD 10章の `failed`(削除が完了しなかった場合)の文言を広げる必要があるか、ユーザーに確認する。
- PD 4.7 の「エラー(案。SDで確定)」と SD の `delete_error`(案)は、確定するまで「案」のまま。
- 修正後の SD の再レビュー(フェーズ5の再確認)、相互参照の最終確認、task-reviewer。

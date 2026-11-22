# 0047 SD v0.7 再レビュー指摘の反映(`stale` 廃止、`failed` の範囲拡大)

## 概要
プラン 0041 のフェーズ5の再確認。document-reviewer が修正後の SD v0.7 を再レビューした(Critical なし。Important 5、Suggestion 4、Nitpick 2。D-1〜D-46 の ID 列挙は突合できた。PD の小修正は妥当)。指摘のうち仕様判断が要る2点をユーザーに確認し(下記)、document-writer が SD v0.7 と PD v0.13 に反映した。

## ユーザー回答(2026-11-09、確定)
- A. `stale` を廃止し `superseded` に一本化する(推奨案)。理由: 新しい開始通知が `finish_received_at` の無い旧い結果をすべて `superseded` にするため、`stale` は到達しない。
- B. `failed` の範囲に、クロールの失敗・取り消しで削除を行わなかった場合(`outcome_failed`、`outcome_cancelled`)を含める(推奨案)。

## 変更したファイル
- `docs/v0.x/system-design/system-design-v0.7.md`
- `docs/v0.x/product-design/product-design-v0.13.md`

## 変更内容
- A: 受理時の分岐を(1)終端状態、(2)未知の `crawl_id`、(3)`failed`/`cancelled`、(4)`enumeration_completed` の4つにした。終端状態(`superseded` など)の結果への遅れた終了通知は何もしない(202)。`discarded` の理由は `superseded` と `source_deleted` の2つ。状態表、判定表、競合表、用語集、§4.5、§14.2、§14.5、§14.7、E-10、D-6、D-11、D-39、§11.12 を整合。
- B: PD の改訂履歴 v0.13、4.7、4.7 末尾の確認事項、10章の「削除結果」を「削除が行われなかった、または完了しなかった場合」に広げた。SD:23 に「PD と一致しており食い違いではない」と追記。
- 再レビュー指摘:
  1. 記録済みの終了通知の再送は世代を見ず冪等。`finish_received_at` の永続化は `enumeration_completed` の受理に限定(`failed`/`cancelled` では記録せず `failed` にする)。
  2. ソース削除の停止: 自分の結果が読めない(404)、または条件付き更新が失敗した場合も書き換えずに止まる(§1.2、§3.9、D-41)。
  3. `discarded` 書き込みの衝突は、読み直して再試行(§1.2、§3.9、§12.5)。
  4. 待機から判定への遷移で `deletion_started_at` を `if_seq_no` つきで書く(案)。判定表の順2〜6に確認の注記。
  5. 設定スナップショットの複写と件数照合の許容は「案Bに含まれ方式は承認済み、細部は案」に直した。
  6. E-18 に「届かなければ `running` のまま(次の開始通知で `superseded`)」を追記。
  7. 開始通知の判定順序: 終端状態の `crawl_id` は409 → 同じ `crawl_id` で `running` なら成功 → 現行世代より古い `crawl_started_at` なら409。
  8. 待機中の結果を進める契機(イベントか定期走査か)は実装時に決める(§12.5)。
  9. D-12 の `interrupted` の語を削除。
  10. PD 237 末尾の括弧を削除。433 を「SD v0.6・v0.7に存在せず」に修正。
- §12.3 に「`stale` の廃止」の行、§14.7 に A・B のユーザー確定の行を追加。冒頭と改訂履歴 v0.7 に反映。

## grep の結果
- PD v0.13: `stale`・`interrupted`・`世代確認` は残っていない。
- SD v0.7: `stale`・`interrupted` は経緯・過去版の説明・廃止の記録としてのみ残る。`世代確認` は642行に過去版への言及が1か所。
- D-1〜D-46(D-18 欠番)の ID 列挙は崩れていない。

## 判断・留意点
- `failed`/`cancelled` の終了通知は `finish_received_at` を記録しない(既存記述に合わせた)。再送は「結果が終端状態であること」で冪等にしている。
- 案のまま残した細部: `waiting_for`、`failed` の理由コード一覧、`if_seq_no`、`deletion_started_at`、直列処理の方式の細部。
- PD v0.12 から持ち越した3項目(しきい値の入力検証、「結果未確認／不明」の表示ルール、登録結果の保持場所とAPI。PD 9.2 #9、#11、#12)は、範囲外としてSDに未反映。

## 未対応事項
- 相互参照の最終確認(PD→SD v0.7、SD→PD v0.13)と task-reviewer による全体確認。
- PD 4.7 の「エラー(案。SDで確定)」と SD の `delete_error`(案)は、確定するまで「案」のまま。

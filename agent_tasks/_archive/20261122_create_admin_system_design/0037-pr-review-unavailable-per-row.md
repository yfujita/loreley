# 0037 PR #10 レビュー指摘: 一覧の `unavailable` が行単位の失敗を区別できない

日付: 2026-11-23
起点: ユーザーが貼り付けたレビュー指摘([P2]。`admin-api-v0.1.md` L154–159)。「指摘が適切であれば対応して」という指示

## 指摘

一覧の `unavailable` は最上位に置き、「その項目の取得に 1 行でも失敗した」ことを示す。しかし行の `null` は「取得失敗」と「値がない」の両方に使うため、`last_crawl: null` の 2 行(未クロールの `source-a`、読み取りに失敗した `source-b`)を区別できない。フロントエンド設計も両方を「取得できません」とする。R-3 のように一括検索全体の成否だけなら問題が表面化しないが、行単位の部分失敗を許すなら API 契約として情報が不足。推奨は、行に `unavailable` を持たせる、または全件成功・全件失敗だけとして行単位の部分失敗をサポートしないと明記する。

## 妥当性の確認(メイン)

- B 2.2 は「一覧の EP では、キーは 1 行でも失敗したことを表し、どの行が `null` かは行の中の値で決まる」と書く。**行内の `null` は「値がない」場合にも使われる**(B 2.2 の末尾の規則)ため、指摘のとおり行を区別できない。
- 行単位の失敗は現実に起こりうる: C 5.8(517 行)は「`msearch` のサブ要求のエラー(`responses[i].error`)は対象別に `store_unavailable` / `search_index_unavailable`、`msearch` 全体が例外なら全サブ要求が同じ理由で失敗」と書き、EP-01 の `items[].document_count`・`items[].last_crawl` 系(R-3・R-9 のソースごとのサブ要求)、EP-09 の `items[].stalled`・`latest_for_source`・`rerunnable`(ロック読み取りの失敗)は、行ごとに成否が分かれる。
- したがって「全件成功・全件失敗しかない」と明記する選択肢は取れない。**行に `unavailable` を持たせる**。

## 決定(案。ゲート3で承認済みの AAPI-P-16・25・27・30 の修正=レビュー指摘への対応。ユーザー指示 2026-11-23 に基づく)

- **一覧の EP(EP-01・EP-09・EP-11)の各要素 `items[i]` に `unavailable` オブジェクトを持たせる**。常に存在する(失敗がなければ `{}`)。キーは**その行の中の項目の相対パス**(例: `last_crawl`・`last_crawl.stalled`・`last_completed_at`・`delete_job`・`delete_job.stalled`・`document_count`・`stalled`・`latest_for_source`・`rerunnable`・`existence`)、値は理由コード(`store_unavailable`・`search_index_unavailable`・`timeout`・`malformed`)。
- 一覧の EP の最上位 `unavailable` は、行に属さない最上位の項目(例: EP-11 の `tab_counts.skipped` など)だけを載せる(常に存在。`{}` あり)。`items[].…` 形式のキーは廃止。
- 単一オブジェクトの応答(EP-02・EP-10・EP-12・EP-13・EP-14)は変えない(最上位の `unavailable`、キーは応答の項目の正式なパス)。
- 規則: 「`null` で、その行(または最上位)の `unavailable` にキーがある」=取得できなかった、「キーがない `null`」=値がない(または読めない値=読めない `null`)。EP-01 の主たる読み取り(R-1)の失敗や、一括検索の全体が失敗したときは、**全行の `unavailable` に同じキーを付ける**(最上位ではなく行に)。
- 影響範囲: B(2.2・2.11・EP-01・EP-09・EP-11・11 章の AAPI-P-16・25・27・30・JSON 例・検算)、A(5.2 の `unavailable` の記述があれば)、C(5.4・5.8・5.10・3.3 の R-3・R-9・R-11・テスト観点 6)、D(DTO・組み立て 1 か所の説明)、E(5.7・5.9・6 章の `unavailable` の引き方)、F(`unavailable.ts` の `cellState`・`expectedFields`・FMOD-P-14・P-31・テスト)。OpenAPI の DTO に行の `unavailable` を足す(型生成に影響)。

## 進め方

1. B・A の修正(B 担当 writer)
2. C・D の修正、E・F の修正(それぞれの担当 writer。並行)
3. 機械チェックと、変更箇所の差分確認
4. `feature/admin-system-design` ブランチにコミットして push(PR #10 に反映)

## 備考

- ユーザー承認済み(ゲート3)の ID(AAPI-P-16・25・27・30)の内容変更になるため、完了報告で明示する。区分は「承認済みの案(ゲート3)の修正(PR レビュー指摘への対応)」とし、確定にはしない

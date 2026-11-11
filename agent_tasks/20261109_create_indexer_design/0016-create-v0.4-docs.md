# 0016 v0.4 の作成 作業記録

## 概要
0015 のプランに基づき、document-writer 3体が Indexer 5文書の v0.4 を新規ファイルで並行作成した。v0.3 以前は変更していない。SD・旧版・「変更点」章への言及なし(各担当が grep で確認。architecture はプロダクト設計 v0.14 への言及の `v0.14` が正規表現に一致しただけで、実質0件)。ユーザー未確定の設計判断はすべて「案」「未決」とし、K12 と P31 の文面は変更していない。

## 作成したファイル
- docs/v0.x/system-design/indexer/indexer-architecture-v0.4.md
- docs/v0.x/system-design/indexer/indexer-api-v0.4.md
- docs/v0.x/system-design/opensearch/schema/search-index-v0.4.md
- docs/v0.x/system-design/opensearch/schema/loreley-texts-v0.4.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.4.md

## 反映内容(案の ID は architecture 17章)
- ① P26 改訂(メタデータ分離): (a)経路で Store 層とメタデータ(title、source_updated_at、mime_type、size。url/path は U-1 確定後)の差分を比較し、差分があれば if_seq_no 付きで Store 層のメタデータだけを検索 upsert より先に部分更新。text・要約・index_status には触れず pending_index にも遷移しない。失敗時は文書単位の失敗とし次回クロールで再比較(担当の補足。案)。要約保存との seq_no 衝突は読み直して再試行。C-10 の文言修正、C-14(メタデータだけ変更)追加。U-17 は一部解消。
- ② P35 text_hash(案): 抽出後 text の SHA-256 を Store 層(`text_hash`、`summary_text_hash`)と検索インデックス(`text_hash`)に持つ。算出対象は切り詰め後の Store `text` の UTF-8 バイト列、16進小文字(案)。要約の Store 保存は content_hash 条件 AND text_hash 一致 AND if_seq_no、検索への要約反映は両ハッシュ一致のスクリプト条件(原子的)。再構築では summary_text_hash == text_hash の要約のみ保持。P26 の判定は直接比較のまま。7.2 の確定文言は変えない。U-9 を P35 で扱う案に更新。C-12、C-13、R-5 更新、C-15(text_hash 不一致の破棄)・C-16(seq_no 衝突)追加。
- ⑤ P33 改訂: 判定時刻を固定(cutoff=判定時刻−TTL)し、document_id ソートの search_after で全 ID を取り込みメモリ保持。T=取り込み件数、deleted_count<=T、PIT は必須にしない。100万件以上は 15.4 の実測項目。D-76 更新。
- ⑥ P36: バッチ登録・last-seen の crawl_started_at を deletion_result-{crawl_id} の複写値と照合。不一致はリクエスト全体のエラー(非リトライ、ジョブ failed。409 `crawl_started_at_mismatch`、案)。deletion_result がない場合は拒否してジョブ failed(409 `crawl_not_started`、案)。照合は所有確認や文書ごとの処理より前に1回。API-U-18 は「検証する(案)」に更新、API-U-19 新設。D-77、D-78 追加。
- ③ U-27: プロダクト設計 v0.14 5.2 の4(検索のみの文書は削除する)との差分を明記(8.1 とは衝突しない)。P28 採用時の統一文面を案として併記。プロダクト設計は未修正。
- ⑦: ソース削除の 4.7・4.8 相当は冪等で再実行できる。リース切れの lock_not_owned でジョブは failed で止まり再実行で完了。どちらのロックの扱いでも Indexer 側は正しい。ロック採否は Crawler 領域として未決。E-43(ソース削除の再実行)追加。
- ⑧: search-index 2.5 と loreley-texts 2.3 にフィールド対応表(Crawler 入力→Store 層→検索インデックス→書き込み主体→再構築可否)を追加。再構築で作れないものは last_seen_at(初期化)、url/path、fetched_at/metadata、summary_embedding、acl。loreley-deletions 2.3 に入力(開始・終了通知)→記録の対応表。マッピング JSON に text_hash を追加。
- ④ P31: 文面は現状維持(ユーザー確認待ち)。

## 担当エージェントによる補足(すべて案)
- メタデータ更新失敗時は全文 upsert に進まず文書単位の失敗とする。
- 4.8 の `deleted` は、記録がすでにない場合は false で成功。再実行を成り立たせるための補足。
- 「メタデータのみ更新」を change の `updated` に数えるかは未決(API-U-9、API-U-16)。
- deletion_result が終端状態のときの登録要請の扱いは未記載(architecture U-4 で詰める余地)。
- 9.8 の PIT 非必須の根拠(document_id ソートで取りこぼし・重複が起きない)は推測と明記。
- loreley-deletions では skipped_document_ids / oversize_document_ids の ID リスト自体の保存先は「本書では未記載」。
- 0015 が「U-1」と記した url/path は、architecture では U-16(U-1 は数値の既定値)。

## 未対応事項
- 5文書の整合確認と妥当性レビュー(document-reviewer)は未実施。特に architecture と api の P35/P36/U-27 の参照、api の 4.2/4.3 の実記述と architecture 9.5 の整合、メタデータ更新失敗時の記述の一致。
- ユーザー判断待ち: P31(K12 の適用範囲。承認が必須)、P35(text_hash 導入)、P26 のメタデータ分離、P28 とプロダクト設計 5.2 の統一(プロダクト設計の修正)、ソース削除ジョブのロック(Crawler 領域)、U-1(url/path)、P36 の必須化と応答コード名、P32(拒否主体)、P34(409 廃止)、U-21(loreley-texts 廃止)。

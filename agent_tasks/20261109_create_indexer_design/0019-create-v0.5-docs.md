# 0019 v0.5 の作成 作業記録

## 概要
0018 のプランに基づき、document-writer 2体が Indexer 5文書の v0.5 を新規ファイルで並行作成した(architecture / api と Schema 3文書)。v0.4 以前は変更していない。外部レビューの推奨を取り入れた記述はすべて「案(推奨。ユーザー承認待ち)」とし、確定欄(K 系)には移していない。K12 の本文は変更していない。プロダクト設計 v0.14 は変更していない。各担当が grep(SD・system-design-v・§・L行番号・変更点・v0.1〜0.4・従来)で0件を確認。

## 作成したファイル
- docs/v0.x/system-design/indexer/indexer-architecture-v0.5.md
- docs/v0.x/system-design/indexer/indexer-api-v0.5.md
- docs/v0.x/system-design/opensearch/schema/search-index-v0.5.md
- docs/v0.x/system-design/opensearch/schema/loreley-texts-v0.5.md
- docs/v0.x/system-design/opensearch/schema/loreley-deletions-v0.5.md

## 反映内容
- P36 改訂(案): 受理条件は deletion_result が存在、source_id 一致、crawl_started_at 一致、status==running、finish_received_at が存在しない、Crawler のロック所有確認に成功。終端状態(superseded/discarded/failed/受理済み)への登録は拒否(v0.4 の「一致すれば受理」から変更)。保持期間超過で消えた deletion_result は「存在しない」で拒否に統一。通常クロールでは crawl_id・crawl_started_at 必須、突合・ソース削除は別エンドポイントまたは明示の purpose で区別。拒否は不一致/結果なし/終端/受理後の4種。api のエラー名(案): crawl_started_at_mismatch、crawl_not_started、crawl_source_mismatch、crawl_already_closed、crawl_finished。U-28 の(c)は「拒否(推奨。ユーザー承認待ち)」。
- P37 新規(案): 開始通知の再送は、同じ crawl_id で running のとき deletion_result に複写済みの6項目と直接比較。一致なら成功、不一致なら 409(api の名称案 crawl_start_conflict。状態は変えない)。
- P34: 本文は現行の案A(再送は常に 202、先着採用)のまま。案B(異なる内容は 409。ダイジェスト保存と Crawler の固定義務。api の名称案 finish_content_mismatch)を architecture U-29 / API-U-21 に並記。ユーザー判断。
- P33: 保証を「同一リフレッシュ後に取得(スナップショットの保証はしない)」に弱めた。T>D は既存の validation_failed として削除を見送る(案。強制削除モードでも確認)。D-85・D-86 追加。
- P31: K12 の改訂文案を「案(K12 の改訂案。ユーザー承認待ち)」として併記。K12 の書き直しと PD v0.14 の2章・4.2・5.2の1・8.2・受入基準の同期はユーザー承認後で、Indexer 文書では行わないと明記。
- P35: text_hash は text と同じ書き込み(4.3 手順3の text 書き込み)で更新し、確定更新(手順4)では更新しない。
- 9.14 ソース削除ロック: Crawler 向け要件(リース更新の継続、所有権喪失時の後続停止、再実行で復旧、削除中のソースに新クロールを起動しない)を案で追記。「削除中」状態の置き場所は未決。
- U-16(url/path): 2項目(url=アクセス可能な原文 URL、path=データソース内パス。独立した任意項目)を案(推奨)に。マッピング JSON に url/path(keyword、index:false の案)を追加し、dynamic: strict の注意書きを更新。path の検索・絞り込みと最大長は未決(search-index U-8)。
- U-21: loreley-texts は存続(推奨。ユーザー確認待ち)。確定欄に移していない。
- P28/U-27: PD 5.2 の4 との差分と統一文面案を維持(PD は未修正)。
- P38 新規(案): change を created / updated(本文またはメタデータの変更)/ unchanged(内容が同じで再登録のみ)に。unchanged_count を Crawler 領域の集計項目に。last-seen の result.unchanged との用語区別。応答喪失時の集計は厳密でないこと、再送時は Crawler が最初に受け取れた結果を保持すること。pending_index/extract_failed の再処理を updated とする点は推測と注記。
- テスト追加: architecture D-79〜D-86、C-17。

## 新規/更新 ID
- architecture: 新規 P37、P38、U-29、D-79〜D-86、C-17。更新 P2、P31、P33、P34、P35、P36、U-16、U-21、U-27、U-28。
- api: 新規 API-U-20(P37)、API-U-21(P34 の案A/案B)。更新 API-U-3, 9, 11, 12, 14, 16, 18, 19。
- search-index: 新規 U-8。loreley-deletions: 新規 U-9(P37)。

## 担当エージェントによる補足(案)
- 受理条件のうち存在・source_id・crawl_started_at・status・finish_received_at はリクエスト先頭で1回、ロック所有確認だけ文書ごと。
- 手順番号: 依頼文の「4.3 手順2/3」は v0.4 の番号と合わず、実際の番号に合わせて記載(text 書き込みは手順3、確定更新は手順4)。
- 0018 の「U-1/U-16」のうち url/path は U-16(U-1 は数値既定値)。
- エラー名・purpose の値・案Bの 409 名は担当エージェントの命名案で、api と architecture で名称の突き合わせが必要。

## 未対応事項
- 5文書の整合確認と妥当性レビュー(document-reviewer)は未実施(api/schema 担当は architecture v0.5 の完成前に作成したため、P/U/D 番号・T>D の記載・エラー名の突き合わせが未了)。
- task-reviewer による全体確認(v0.5 を含む)は未実施。
- ユーザー承認待ち: P31/K12 の書き直し(PD の同期を含む)、P28 と PD 5.2 の4 の統一、P36(終端状態の拒否)、P34 の案A/案B、ソース削除ロック(Crawler 設計)、U-1 url/path 2項目、P35、P38、U-21 存続、P37。

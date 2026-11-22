# 0012 設計書 v0.2 の作成とレビュー反映

- 日付: 2026-11-13
- 実施: 0011 のプランに沿って、v0.1 の 6 本を v0.2 として改版し、決定事項の文書を新規追加した(document-writer による作成。メインは複写・ID 照合・13.7/13.8 の小修正)。第 1 回レビュー(観点 A・B の 2 名)の指摘を反映し、再確認レビュー(1 名)を実施
- 結果: 下記。v0.1 の 6 本は変更していない(git 管理下で差分なし)

## 成果物(`docs/v0.x/system-design/crawler/`)

- `crawler-architecture-v0.2.md`(1166 行)、`crawler-api-v0.2.md`(584 行)、`crawler-module-structure-v0.2.md`(916 行)
- `connector/connector-interface-v0.2.md`(466 行)、`connector/connector-file-system-v0.2.md`(756 行)、`connector/connector-web-v0.2.md`(292 行)
- `crawler-design-decisions-v0.1.md`(171 行。新規。実装着手のための短い決定事項の要約。何も新たに決めない)

## 外部レビュー 7 点+構成 2 点の反映(0011 の評価どおり)

- ① 設定の 1 回読み: 手順 6 の順序を「リース設定 → `queued`→`running` → `loreley-sources` を 1 度だけ読む → `settings_snapshot` と `settings_source_updated_at`(`settings_snapshot` の外。案)を追記」に変更。`connector_config` はメモリのみ(CA-P-51)
- ② 0 件警告(CA-P-52)と、削除の保留の新規の未決 CA-U-19(選択肢 (a)〜(c)。推奨 (a)。確定扱いにしない)、FS 3.4 の確認手順と目印ファイル案(CFS-P-23・24、CFS-U-7)
- ③ 索引・マッピング: `opensearch-init` が作成・管理(CA-K-21、CM-K-9。ユーザー確定 0010)。既存索引は更新されないため、前提作業に put mapping か既存ボリュームの作り直しを含める(案)
- ④ Repository の全件走査・バルク削除・refresh の契約(CA-P-53)、ソース削除の順 3 の条件指定の削除(CA-P-54。案)、10,001 件以上の統合テスト
- ⑤ 設定の削除=ソース削除ジョブ(CA-K-22、CAPI-K-8。ユーザー確定 0010)
- ⑥ 識別子エラーの削除判定への影響を 7.7 に明記、CA-U-7 に選択肢(新規の抑止は未決)
- ⑦ 起動時の整合性検査(CA-P-55。Indexer の設定名に対応する値を compose で Crawler にも渡す。名前と未設定の扱いは CM-U-9)
- 構成: `crawler-design-decisions-v0.1.md` を追加。`include_patterns` は確定せず、CFS-U-1 に選択肢(追加/置き換え/名称変更)と Admin View の注意を追記

## 新規・解消した ID

- 新規: CA-K-21・22、CA-P-51〜55、CA-U-19、CAPI-K-8、CM-K-9、CM-P-22〜25、CM-U-9、CFS-P-23・24、CFS-U-7
- 解消(番号は残す): CA-U-11、I-6、CM-U-7、CAPI-P-11(→CAPI-K-8)、CAPI-U-1 の「Q1 の解釈の確認」の部分

## 第 1 回レビューの指摘と反映

- Important(観点 A): (1) 手順 6 の失敗時の遷移が未定義(`queued` のまま失敗)→ 順序を `running` 先に変更。(2) 環境変数名が実際の `LORELEY_INDEXER_` 接頭辞と食い違い、記述どうしも矛盾 → 「Indexer の設定名に対応する値を compose で渡す」に統一。未設定時の素通りを限界として明示(CM-U-9)。(3) `opensearch-init` が既存索引を更新しない → 前提作業に追加(案)
- Important(観点 B、decisions と FS): 確定の行への案・導出の混在、CA-U-19 の選択肢の誤要約、略称「api 3.5」の誤り、2 章に案が方針として載っていない、`warnings` の表示経路の誤り(Admin API が `loreley-jobs` を直接読む。CA-U-12)→ すべて反映
- Suggestion・Nitpick: `config_updated_at` を `settings_snapshot` の外に出して `settings_source_updated_at` に改名(CA-K-5 の 6 項目を守る)、タイブレークの第一候補を keyword 項目に、操作一覧・タイムアウト・`last-seen` 分割の上限の明確化 ほか。反映済み

## 判断・乖離の記録

- 0000 の成果物は 6 本だが、7 本目の `crawler-design-decisions-v0.1.md` を追加した。ユーザーが貼り付けた外部レビューの提案(構成の所感)を、「確認して指摘が適切であれば改善した新版を作成して」の指示のもとで採用した。ユーザーの明示的な確認は取っていない(不要なら削除可)
- 前提作業(`infra/opensearch/schema/` の変更)は、この設計タスクでは行わない。実装タスクで行う(Indexer の結合テストが同じ `jobs.json` を使うため、同時更新が要る)
- 第 1 回レビュー後の修正に対しては、今回は独立した再確認レビューを実施した(0009 で省略した反省を踏まえた。結果は下記)
- 機械チェック: 全文書の ID 参照・定義(CA/CAPI/CI/CFS/CW/CM)に参照切れ・欠番なし。旧名・旧記述の残存なし(architecture 13.7 の履歴言及を除く)

## 未対応事項・ユーザー判断待ち

- 0009 の第 2 群(実装前)の残りは未回答のまま(`source_id` の文字種、glob と `include_patterns` の意味、`external_id` 衝突時の `failed`、「削除中」の置き場所、連続スキップの取得段階への拡張、ソース削除中のメンテナンス確認、設定の必須・全置換 など)。新規の CA-U-19(0 件列挙時の削除の保留)も判断待ち
- 実機未確認: PIT・`search_after`・`_shard_doc`・条件指定の削除・put mapping(CA-U-18)、mermaid の描画
- 設計書はすべてユーザー未承認(v0.2/decisions v0.1)。承認後の変更は新版で

## 再確認レビューの結果と反映

- 再確認レビュー(document-reviewer 1 名。手順 6 の順序・項目名・環境変数名・前提作業・タイブレーク・区分・反映済み表示・mermaid 構文を横断確認): Critical 0 / Important 3 / Suggestion 6 / Nitpick 7。すべて反映
  - Important: (1) 全件走査のタイブレーク `document_id` は、同じソースの skip と oversize が同じ `document_id` で共存すると同順位になる(10,001 件以上で `search_after` が破綻)→ **全件走査は `record_type` ごとに 1 回ずつ行う**に変更(architecture 3.1・6.4・8.1 順 3・テスト #37、module-structure 4.8・CM-P-24、decisions 5 章)。(2) decisions が「何も決めない」に反して新しい推奨・UI 要件を加えていた → 削除し、出典のある記述に置換。(3) module-structure 3 章の Indexer 環境変数名の接頭辞の誤記 → 修正
  - Suggestion: 手順 6 の中間状態(リース設定後・`running` 前の停止)の 5.1・5.4・5.8 への反映、前提作業に `init-indices.sh` への `loreley-sources` の追加(案)、テスト #39 の検査項目の補完、13.8 の CM-U-6・CM-U-1 の同期、web の CA-U-19 (b) の表記統一、13.7 の反映状況 ほか
- 反映後の機械チェック: 全文書の ID 参照・定義(CA/CAPI/CI/CFS/CW/CM)に参照切れなし。旧名 `config_updated_at` は decisions の「旧名は使わない」の 1 か所のみ。13.7 の「残る依頼」はなし
- 反映後の独立した再レビューは行っていない(再確認レビューの指摘は局所的で、全件機械チェックと担当ライターの突き合わせで確認)。必要なら、`record_type` ごとの走査と手順 6 中間状態(5.1・5.4・5.8)の変更箇所だけの軽量な再確認を 1 回追加できる

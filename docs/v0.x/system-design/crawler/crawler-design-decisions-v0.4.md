# Crawler 決定事項(実装着手のための要約)v0.4

- 版: v0.4
- 更新日: 2026-11-16
- 前版: `crawler-design-decisions-v0.3.md`
- v0.4 の改訂(2026-11-16。出典: ユーザー指示 2026-11-16「未確認事項について、設計書は承認する。2設計書の改版に反映する。それ以外は別タスク」と、作業記録 `agent_tasks/20261113_implement_crawler/0023-approve-and-revise-design.md`(以下「0023」)。この文書は何も決めず、各新版の区分を写しただけ):
  - **承認の反映**: ユーザー指示の「未確認事項」は、タスクの STATUS.md「ユーザー判断待ち」の項目で、その 1「設計書の承認」は、Crawler 設計書の現行版全体(architecture・crawler-api・module-structure・decisions と、connector 配下の interface・file-system・web)と、v0.3 の4章の「ユーザー判断待ち」10件の承認を指す。指示中の「2設計書の改版」は、判断待ち 2「設計書の改版」(改版依頼の反映)の意で、「2設計書」ではない。「それ以外は別タスク」は判断待ち 3〜5(infra 前提作業の起票、コミット、Integration Test)の意。
    - 解釈: 現行版全体を承認し、これまで「案」(`-P-`)だったものは**承認済みの案**(変更にはユーザー判断が要る)として扱う。ID は付け替えず `-P-` のまま。承認は確定(`-K-`)への格上げではなく、数値(仮値)の承認でもない。
    - ただし、**4章の表の ID 列(v0.3 の4章の10件と CM-U-4・CA-U-3)にない未決(`-U-`)は、新たに解消していない**。対応する `-P-` が承認済みでも、`-U-` に残る論点(実測、Admin API 設計時の決定、ユーザーの個別判断、細部の最終決定、実機確認)が残る。5章で残る論点を一文で示す。未回答の判断を承認扱いにしない原則は変わらず、承認されたのは 2026-11-16 のユーザー指示の範囲だけである。
  - **4章**: v0.3 の「ユーザー判断待ち」10件と CM-U-4・CA-U-3 は、設計書の案どおりで承認された(実装も案どおり)。表を「2026-11-16 に承認」に改め、ID 列は各新版が「正本」として参照するので、そのまま残した。実装の局所化箇所は作業記録 0021 §2 を参照する形にした。
  - **5章**: 実装完了後の状態に書き直した。実装担当が決めた内容は各新版の新規 ID(CA-P-56〜76、CAPI-P-20〜28、CAPI-U-11・12、CM-P-28〜37、CFS-P-25〜31、CI-P-18。CAPI-P-29 は 2026-11-16 の追補)へのポインタにし、なお未決のものを列挙した。実装で決めた内容は、ユーザーの確定でも承認でもない。
  - 変更した節: 冒頭(略称・設計書の版)、1〜5章、7章(I-5・I-8 の注記)、8章(#40〜#43 を追加)、9章(区分の更新)、10章(参照先を新版に更新、実装の場所)。2章は区分の表記、参照 ID、方針 #8・9・12・13・15 の注記の更新だけ(方針は変えていない)。3章は区分の表記と CM-K-11 の注記。6章は変更なし。
  - 解消(案どおり承認): CAPI-U-4・CA-U-15、CFS-U-1、CA-U-6・CI-U-2・CFS-U-5、CA-U-2、CA-U-16、CA-U-17、CAPI-U-3・CAPI-U-8・CAPI-U-1 のうち Crawler が 409 を返す点、CA-U-7・CA-U-4、CFS-U-2・CFS-U-3、CA-U-19・CFS-U-7(案 (a) 現状維持。(b)(c) は採らない)、CM-U-4、CA-U-3。うち CAPI-U-1・3・4・8、CA-U-4 は一部の解消で、残る部分は各新版のとおり未決(5章)。実装で決めた(承認ではない): CM-U-2(CM-P-29)。
  - **追補(2026-11-16。出典: ユーザーの回答。作業記録 0024)**: 0023 の確認への回答で、承認の範囲の解釈は「上の解釈でよい」とされ、CA-U-20(滅多に起こらないのでシンプルな形がいい。専用の経路を置かない)・CAPI-U-11(int64 範囲外は考えなくてよい)・CAPI-U-12(一旦 10M。10 MiB と解釈。仮値)がユーザーの個別判断で解消した。5章の該当行と「決めてはいけない」を更新した。この文書は何も決めず、各新版の区分を写しただけ。
  - **追補(2026-11-16。出典: ユーザーの回答。作業記録 0025)**: 未決事項の対話でのユーザーの回答を各新版にその場で反映した(各文書の追補が正本。この文書は何も決めず、各新版の区分を写しただけ)。承認の表記は「案どおり承認」「ユーザー回答 2026-11-16」で、確定(`-K-`)への付け替えではない。(1) **定期起動の周期は cron 式に置き換わった**(`schedule_interval_seconds` を廃止し `schedule_cron` に。architecture CA-U-8 の解消、CA-P-12)。ユーザー回答の範囲は、cron 式、標準の 5 項目(秒なし)、タイムゾーンは環境変数 1 つ、項目名 `schedule_cron`、解釈にライブラリを使う、止まっていた分は起動しない。**ユーザー未確認のメインの提案**は、別名の拒否、環境変数名 `LORELEY_CRAWLER_TIMEZONE`、IANA 名・未設定は UTC、検証の絞り込み、起動の判定の実装(architecture CA-P-77、crawler-api CAPI-P-30、module-structure CM-P-38)。(2) **解消した ID**(内容は各新版の追補が正本): CA-U-4・5・7・8・9・13、CA-U-14 の Crawler 側、CAPI-U-2・4・7・8、CM-U-3・9、CI-U-1・4・6。CI-U-3 は `error_count` の定義が決まり、上限値などの数値(仮値)が残る。5章の表と「決めてはいけない」を更新した。CA-U-20・CAPI-U-11・12 は上の追補(作業記録 0024)で解消済み。
  - 新規 ID: この文書は ID を持たない。各新版の新規 ID(CA-P-56〜76、CA-U-20、CAPI-P-20〜29、CAPI-U-11・12、CM-P-28〜37、CFS-P-25〜31、CI-P-18)は5章でポインタにした。追補(2026-11-16)の新規 ID は、提案(ユーザー未確認)の CA-P-77・CAPI-P-30・CM-P-38。
- v0.3 の改訂: Crawler にヘルスチェック用の API を置くことが確定した(ユーザー回答 2026-11-13。出典は `agent_tasks/20261113_implement_crawler/0003-plan-approval-and-healthz-update.md` の §1)ことへの追従だけ。確定は「置く」ことだけで、`GET /healthz` というパス・メソッド、応答の形、動作などの詳細は案だった(module CM-P-27、api 4.7)。CM-U-5・CAPI-U-9 を解消した。
- v0.2 の改訂: module-structure v0.3 への追従だけ。`connectors` を `infrastructure` の外の独立したモジュールにした(ユーザーの指示。CM-K-10)。
- 位置づけ: Crawler 設計書 6 本(下の 10 章)の**要約**。実装担当(エージェント)が「何が確定・承認済みで、何がなお未決か」「どこまで自律的に決めてよいか」を判断するための短い文書で、詳細は書き写さず、ID と章番号で参照する。
- **この文書は何も決めない**。確定・案・未決を新たに作らず、各設計書の区分をそのまま写す。正本は各設計書で、食い違いがあれば各設計書を正とし、この文書を直す。この文書は ID を持たない。
- 区分は architecture v0.4 冒頭の凡例に合わせる(確定=ユーザー確定、案=v0.4 から**承認済みの案**、未決、推測、導出)。**確定にしてよいのは、各設計書が確定(CA-K など)としているものだけ**。承認済みの案を確定として書かない。
- 承認と、ユーザーの回答・指示の範囲: 設計書 6 本(architecture v0.4・api v0.4・module v0.5・FS v0.3・interface v0.3・Web v0.3)は、2026-11-16 のユーザー承認を受けた版である。この Crawler 設計でのユーザー回答は、Q1〜Q3 と、2026-11-13 の 3 点(索引・マッピングの作成担当、設定の削除の解釈、`connectors` を独立したモジュールにすること)、実装タスクでの 2026-11-13 の回答(Crawler にヘルスチェック用の API を置くこと。CM-K-11、CAPI-K-9)、2026-11-16 の承認。ほかに、Indexer 設計書・PD でユーザーが承認済みの事項がある(3章で区別する)。
- 略称: architecture=`crawler-architecture-v0.4.md`、api=`crawler-api-v0.4.md`、module=`crawler-module-structure-v0.5.md`、interface=`connector/connector-interface-v0.3.md`、FS=`connector/connector-file-system-v0.3.md`、Web=`connector/connector-web-v0.3.md`。章番号は「architecture 7.5」のように書く。Indexer 設計書は「Indexer api」「Indexer arch」と書く(例: 「Indexer api 3.5」は Indexer の API 設計書の章)。
- 実装の場所: `apps/crawler/`。挙動・環境変数・運用・持ち越しの正本は `apps/crawler/README.md`。

---

## 1. 最初に守ること

1. 承認済みの案は、設計書のとおりに実装する。なお未決のうちユーザー判断が要るものを、実装者が確定しない(5章)。
2. 承認済みの案を変えたいときは、実装で変えずに、設計書の改版(新版ファイル)を提案する。変更にはユーザー判断が要る。
3. Indexer の設計書・実装は変更しない。Indexer 側の課題は報告に書く。ただし、前提作業として `infra/opensearch/schema/` などの変更が要る(4章。ユーザー指示 2026-11-16「それ以外は別タスク」に従い、この改版では扱わない)。
4. 未回答の判断を承認扱いにしない。承認されたのは 2026-11-16 のユーザー指示の範囲(上の v0.4 の改訂と追補)だけで、実装で決めた内容(CA-P-56〜 など)や、承認の対象に含まれない未決は、承認されていない。

## 2. 採用している設計方針

区分欄の「案」は、v0.4 では**承認済みの案**(2026-11-16)を指す。実装で決めた内容(CA-P-56〜 など)は承認の対象外で、ユーザーの確定ではない。

| # | 方針 | 区分 | 参照 |
| --- | --- | --- | --- |
| 1 | 責務分担: Connector は列挙・取得だけ。リトライ・スキップ・Indexer 登録・ジョブ管理・ロックは Crawler 本体。Connector は Indexer・ジョブ・ロックを知らず、内部でリトライしない | 承認済みの案(分担は導出、リトライなしは CI-P-5) | interface 1.4・3.1、architecture 2.2 |
| 2 | 呼び出し順: ロック取得 → 開始通知(列挙前)→ チャンクごとに `last-seen`(取得より前)→ 取得 → バッチ登録 → 全応答を確認して終了通知(202)→ Status API のポーリング | 確定(順序)。チャンクの区切り方は承認済みの案 | CA-K-3、CA-P-16、architecture 4.5・4.6・7.1 |
| 3 | 削除の判断(割合ルール・件数照合・対象決定)と実行は Indexer だけ。Crawler は検索インデックスと削除記録を書かず、期限による削除も要請しない(ソース削除だけが例外)。読まないことも設計原則とする | 確定(削除の判断と実行は Indexer)。読み取りの禁止は導出 | CA-K-2、architecture 1.4・2.2・8章 |
| 4 | 列挙の完全性と削除安全性: 一部でも列挙できなければ `Completed` にせず失敗にする。マウント外れなど全体の異常では文書を削除しない。終了通知の受理前の失敗は削除しない。迷ったらジョブを `failed` にして削除させない | 完全性・受理前の失敗は確定(CFS-K-4、CA-K-9)。「迷ったら `failed`」は導出 | interface 3.3、architecture 1.4・9章 |
| 5 | ジョブの status と削除結果は切り離す。ポーリングの失敗はジョブの status を変えず、確認結果の区分(`confirmed`/`unconfirmed`/`unknown`)を残す | 確定(切り離し)。区分の名称は承認済みの案(CA-P-30) | CA-K-4、architecture 7.6、CA-P-73 |
| 6 | Indexer に見せる値の固定: 設定スナップショットと終了通知の内容はジョブごとに固定し、再送は同じ値。型は strict | 確定 | CA-K-5・CA-K-6 |
| 7 | 設定の読み取りは 1 回: 手順 6 は `running` への遷移 → `loreley-sources` を 1 度だけ読む(`ttl` 等と `connector_config` を同じ版で確定)→ `settings_snapshot` を追記。設定なし・`deleting`・値の欠落・型違いは `config_invalid`(`running` からの `failed`)。`connector_config` はジョブ記録に保存しない。診断用の読んだ版は、`settings_snapshot` の外の最上位項目 `settings_source_updated_at`(旧名 `config_updated_at` は使わない) | 承認済みの案 | CA-P-51、architecture 3.2・3.3.1・4.5 |
| 8 | ロックはソース単位。ハートビートはジョブ実行と独立したスレッド(専用の Store 層クライアント)で、同期 HTTP・Connector の呼び出し中も更新する。所有権を失ったら Indexer への要請を止める。リース切れだけでは自動で引き継がない。ハートビートをジョブごとに作ってそのジョブの実行の間だけスレッドを持たせる点は、実装で決めた内容(module 2.2、CM-P-14) | 承認済みの案(ソース削除の要件は確定: CA-K-11)。並行モデルの最終決定(CA-U-10)は ID 列にないので未決のまま(5章) | CA-P-2〜9、CM-P-13・14、architecture 5章、module 2.2 |
| 9 | リトライ・スキップ: 失敗の種別ごとに `retry` 属性に従う。`write_conflict`・`update_conflict` はリトライして解消しなければ `failed`(スキップしない)。連続 20 件のスキップで打ち切る(取得段階と登録段階は別カウンタ) | 競合の扱いは確定(CA-K-10)。ほかは承認済みの案。20 は仮値・設定可能(承認は仮値の確定ではない) | CA-P-18〜20、CA-P-68、architecture 6章 |
| 10 | Store 層は Repository インターフェース経由。`loreley-jobs` の書き込みは Crawler だけ。`loreley-sources` の登録・更新・削除は Crawler が受ける(Admin API は Crawler の口を呼ぶ)。索引・マッピングの作成は `opensearch-init` | 確定 | CA-K-2・CA-K-19・CA-K-21、CM-K-3・CM-K-4・CM-K-9 |
| 11 | Admin API が `loreley-sources` を読み取りのみで直接読む経路 | 承認済みの案。ユーザー回答 2026-11-16 で、案どおり直接読むことにした(CAPI-U-2 を解消。Crawler に読み取り API は足さない) | CA-P-46、architecture 2.2・2.3 |
| 12 | 0 件列挙の警告と、識別子エラーの削除判定への影響: 観測性と記述の明確化だけで、削除の挙動は変えない。0 件列挙のときの削除の保留は案 (a) 現状維持で承認(CA-U-19。(b)(c) は採らない)。識別子エラーは現行の案(`partially_succeeded`、削除は止めない)で承認(CA-U-7。「1 件でも削除を抑止する」は採らない) | 承認済みの案 | CA-P-52、architecture 7.7 |
| 13 | 10,000 件超の記録の走査・バルク削除(PIT + `search_after`、走査前の refresh)と、Indexer の上限との起動時の整合性検査(Indexer の設定名に対応する値を compose で渡す。Crawler が読む名前は `LORELEY_CRAWLER_INDEXER_<名前>`、未設定は警告して、その項目の検査を省略する。ユーザー回答 2026-11-16。CM-U-9 を解消。CA-P-75、CM-P-34) | 承認済みの案。名前と未設定の扱いはユーザー回答 2026-11-16 で解消(compose で両者に同じ値を渡す定義は、infra の別タスク) | CA-P-53〜55・57・75、architecture 3.1・6.4・10章 |
| 14 | MVP は単一ホスト・単一 Crawler・直列実行(Job Runner が `queued` を 1 件ずつ実行)。実装は Python(Indexer に揃えた構成) | 確定(単一・直列・Python)。構成は承認済みの案 | CM-K-1・CM-K-8、CA-P-11、CM-P-1・19 |
| 15 | モジュール構成: `connectors` は `infrastructure` の配下に置かず、アプリケーション機能の層の独立したモジュールにする(データソースへの接続のほか、クロール対象の管理など複雑な処理を持つため)。必要があれば `connectors` が `infrastructure` を使う。`infrastructure` は `opensearch`・`indexer_client`。`connectors` が Store 層・Indexer クライアント・他のアプリケーション機能に依存しないことは、interface 1.4 と R5 からの導出(承認済みの案)。外部 API のクライアントは Connector が生成せず、`main.py` が Client Factory を作って `ConnectorType` に渡す(承認済みの案。CM-P-26。`create(config)` は変えない)。機械検査(`apps/crawler/tests/architecture/`)は実装で決めた内容(CM-P-37) | 確定(独立したモジュールにすること、必要があれば `infrastructure` を使うこと。CM-K-10)。ほかは承認済みの案 | CM-K-10、CM-P-1・7、module 4.10・6章 |
| 16 | 定期起動: `schedule_cron`(cron 式。標準の 5 項目、秒なし。null は手動のみ)に従う。タイムゾーンは Crawler の環境変数 1 つ(全ソース共通)。Crawler が止まっていた間に過ぎた時刻は起動しない(再開後も)。ロックがあるときは見送り、取り返さない。`status=deleting` は起動しない | ユーザー回答 2026-11-16(上の範囲。CA-P-12 は間隔(秒)から置き換わった。`-P-` のまま)。別名の拒否・環境変数名 `LORELEY_CRAWLER_TIMEZONE`・IANA 名と UTC・検証の絞り込み・起動の判定の実装(メモリ上の前回の判定時刻)は提案(ユーザー未確認。CA-P-77) | CA-P-12・77、CAPI-P-30、CM-P-38、architecture 4.3 |

## 3. ユーザー確定事項(実装者が必ず守るもの)

全件は各設計書の「確定」の表を見る。ここは主要なものだけ。承認(2026-11-16)で確定(`-K-`)に加わったものはない(承認済みの案は `-K-` ではない)。

| 確定 | ID | 実装者が守ること |
| --- | --- | --- |
| Q1 | CA-K-19、CAPI-K-1 | crawler-api は Admin API が呼ぶ口だけ(クロール起動、取り消し、ロック解放、設定の登録・更新・削除、ソース削除ジョブ起動)。Crawler → Indexer の呼び出しは architecture に従う |
| Q2 | CI-K-7、CFS-K-3、CA-K-7 | FS は設定の包含・除外で列挙を絞り、既定は対応拡張子。対象外は列挙も `last_seen_at` の要請もせず、`enumerated_count` に数えない。包含パターンは設定で追加できる(`include_patterns` の意味は 2026-11-16 に「既定拡張子への追加」で承認。CFS-U-1) |
| Q3 | CA-K-20 | 各設計書は末尾に未決・課題を持つ。既存設計との不整合は `I-n`。Indexer 設計書は書き換えない |
| 2026-11-13 | CA-K-21、CM-K-9 | 索引・マッピングは `opensearch-init`(`infra/opensearch/schema/`)が作成・管理する。`loreley-sources` を追加し `loreley-jobs` を拡張する。Indexer が読む 4 項目(`owner`・`job_id`・`lease_expires_at`・`enabled`)の型は維持する。Crawler 側では作らない。個々のマッピング(CA-P-49)は承認済みの案 |
| 2026-11-13 | CA-K-22、CAPI-K-8 | 設定の「削除」はソース削除ジョブの起動(索引済み文書も削除)。設定だけを消す API・操作は置かない。設定の削除は手順の最後 |
| 2026-11-13 | CM-K-10 | `connectors` は `infrastructure` の配下に置かず、アプリケーション機能の層の独立したモジュールにする。データソースへのアクセスに必要があれば `infrastructure` を使う(ここまでが確定)。`opensearch`・`indexer_client`・他のアプリケーション機能に依存しないことは、interface 1.4 と module R5 からの導出で承認済みの案 |
| 2026-11-13(実装タスク。0003 §1) | CM-K-11、CAPI-K-9 | Crawler にヘルスチェック用の API を置く(ここまでが確定。ユーザー回答の原文は「`/healthz` を追加する」)。`GET /healthz` というパス・メソッド、応答の形、動作、Admin API の契約外とする位置づけ、起動順との関係は承認済みの案(module CM-P-27、api 4.7・CAPI-P-19): `api` が担当機能を呼ばず、受付開始後に 200。起動順の最後に受付を始めるため、回復の完了前・整合性検査の失敗時は応答しない。Dockerfile の `HEALTHCHECK` の採用値は実装で決めた内容(CAPI-P-27、CA-P-74。仮値)。compose のヘルスチェックの設定は infra 側の前提作業(別タスク。実装者は決めない) |
| Indexer・PD 由来 | CA-K-1〜6、8〜10 | HTTP で直接通信、呼び出し順、status と削除結果の切り離し、設定スナップショット・終了通知の固定、202 は受理の確認ではない、受理前の失敗は削除しない、競合は `failed` |
| 同上 | CA-K-11・12 | ソース削除はロックを最後まで保持し最後に削除する。リース更新を続け、所有権を失ったら止め、再実行で復旧し、削除中のソースに新しいクロールを起動しない。`DELETE` も `lock` を JSON ボディで送る |
| 同上 | CA-K-13〜18 | ID の検証(空でない・制御文字なし・256 バイト以内)、原本サイズ超過は Crawler と Indexer の両方で拒否、登録結果の集計は Crawler、しきい値の範囲検証は Admin API だけ、`force_delete` は手動実行のみ、Indexer のメンテナンスフラグの読み取りは fail-closed(Crawler 側の読み取りは承認済みの案。CA-P-34) |
| 同上 | CI-K-1〜6、CFS-K-2・4・5・10 | `document_id` と `external_id` の規則、`content_hash`・孤立サロゲート。FS は読み取り専用マウント、列挙失敗では削除しない、0 件列挙は異常にしない、全件更新 |
| 同上 | CM-K-4〜7 | Repository 経由、`DELETE` のボディ、strict な JSON 型、ソース削除中のリース更新 |

注意: CFS-K-6(権限エラーの扱い)は、リトライしない即スキップが承認済みの案で、PD と食い違う(I-8)。CA-K-7 の `enumerated_count` の数え方の定義は承認済みの案。

## 4. 実装着手を妨げる事項(前提作業と、2026-11-16 に承認された判断)

**前提作業**(CA-K-21、CM-K-9。作成・管理の担当は確定): `infra/opensearch/schema/` に `loreley-sources` の索引定義を追加し、`loreley-jobs`(`jobs.json`)を拡張する(マッピング案は architecture 3.1 の表)。`jobs.json` は Indexer の結合テストと共有するため、同時に更新する(CA-K-21)。Indexer が読む 4 項目の型は変えない。

**状態**: Crawler の実装(`apps/crawler/`)は、この前提作業を行わずに完了した。前提作業は、ユーザー指示 2026-11-16「それ以外は別タスク」に従い、この改版では扱わない(判断待ち 3 の別タスク起票は「今は起票しない」。ユーザー回答 2026-11-13)。済むまで、実 OpenSearch ではジョブ・ロックの検索・並べ替えが正しく動かない(`apps/crawler/README.md` 9章)。

加えて、別タスクの前提作業に属する事項(区分を分けて示す。CA-K-21 の確定範囲は担当まで):

- 承認済みの案(architecture 3.1・10章): `infra/opensearch/init-indices.sh` への `loreley-sources` の作成の呼び出しと、索引名の環境変数の追加。既存の環境への反映(`create_index_if_absent` は既存の索引を更新しないため、既存の索引への項目追加(put mapping。`dynamic: false` で足りるかは未確認で CA-U-18)か、既存ボリュームの作り直しのどちらか)。compose の `crawler` サービスの、`opensearch-init` の完了待ちと `:ro` マウント、Indexer の上限値の受け渡し(名前と未設定の扱いは 2026-11-16 のユーザー回答で解消。CM-U-9)。
- 実装で決めた内容(CA-P-74。ユーザーの確定でも承認でもない): `stop_grace_period`(`docker run` なら `--stop-timeout`)は 30 秒以上にする。Dockerfile の `HEALTHCHECK` の採用値(`--start-period` 180 秒など。仮値)。compose の `crawler` サービスの追加自体と、compose のヘルスチェックの設定は別タスクで、本書は値を決めない。
- なお未決(CA-U-14。運用・インフラ設計): `loreley-jobs` の索引名(`JOBS_INDEX_NAME`)を Indexer・`opensearch-init`・Crawler の 3 者に同じ値で渡すこと。

**ユーザー判断の結果**(v0.3 では未回答だった 10 件と CM-U-4・CA-U-3)。**2026-11-16 に、設計書の案どおりで承認された**(ユーザー指示。出典は 0023)。実装もこの案どおりで、変更にはユーザー判断が要る。ID は付け替えない。ID 列は各新版が承認の対象を示す正本として参照する。**各案の実装の局所化箇所(案を変えるときの差し替え箇所)は、作業記録 `agent_tasks/20261113_implement_crawler/0021-final-summary.md` の §2 の表を参照する**。

| # | ID | 内容 | 承認された案 | 備考 |
| --- | --- | --- | --- | --- |
| 1 | CAPI-U-4、CA-U-15 | `source_id` の文字種 | 半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ(CAPI-P-15) | CAPI-U-4 の「表示用の名前の要否」は、追補(2026-11-16)のユーザー回答で解消(表示名の項目は持たせない。管理画面は `source_id` を表示)。後から狭めると互換性の問題 |
| 2 | CFS-U-1 | glob 構文と、`include_patterns` の意味 | glob、既定拡張子への追加(CFS-P-2・3)。置き換え・名称変更は採らない | 変更は FS の改版と既存設定の見直しになる |
| 3 | CA-U-6、CI-U-2、CFS-U-5 | `external_id` 衝突時の扱い | ジョブ `failed`(CA-P-24)。緩和は運用で検討 | 1 組の衝突でそのソースのクロールと期限削除が止まり続ける |
| 4 | CA-U-2 | 「削除中」の置き場所 | `loreley-sources.status=deleting`(CA-P-35) | |
| 5 | CA-U-16 | 連続スキップを取得段階にも広げる | 取得段階と登録段階を別カウンタ(CA-P-20) | Indexer api 3.5・SD v0.8 3.1 にない本設計の独自の拡張 |
| 6 | CA-U-17 | ソース削除中のメンテナンスフラグ確認 | 順 1・2・4 の送信前に確認し、立っていれば `failed`(`maintenance`)。実装での範囲の結論は CA-P-65(順 0・3・5 は対象外) | Indexer arch 11章の開始前チェックに `source_delete` が含まれない点は確認事項として残る |
| 7 | CAPI-U-3、CAPI-U-8、CAPI-U-1(Crawler が 409 を返す点だけ) | 設定項目の必須・更新の全置換、`connector_type` の変更不可、メンテナンス中の応答 | 必須・既定値なし・全置換(CAPI-P-7)、変更不可(CAPI-P-9)、409(CAPI-P-4。crawler-api が返す) | 一部の解消(承認の時点)。追補(2026-11-16)で、`schedule_interval_seconds` の範囲は cron 式への置き換えで該当なし、`external_id` に影響する項目の変更(CAPI-U-8)はユーザー回答で解消(移行処理・警告なし)。`ratio_threshold` の入力単位・既定値(CAPI-U-3)、Admin API 側の 409 の扱いと Admin API 設計の不在(CAPI-U-1)は未決のまま |
| 8 | CA-U-7、CA-U-4 | 識別子エラー文書のジョブ status と記録、原本サイズ超過の記録先・status への影響 | `partially_succeeded`(CA-P-25)、別記録・status に影響なし(CA-P-23) | 「識別子エラー 1 件でも削除を抑止する」は採らない。`error_count` の定義と保持は、追補(2026-11-16)のユーザー回答で解消(抽出失敗の件数のまま。保持は CA-U-5 に従う)。CI-U-4 も同じユーザー回答で解消(識別子エラーは警告のみを受け入れた)。CI-U-3 は、`error_count` の定義が決まり、上限値などの数値(仮値)が実測後に残る(interface 11.4) |
| 9 | CFS-U-2、CFS-U-3 | `follow_symlinks`・`include_hidden` の初期値、`title` の取得元 | 両方 `false`、ファイル名のみ | |
| 10 | CA-U-19、CFS-U-7 | 0 件列挙のときの削除の保留 | 案 (a): 現状維持(PD 5.2 のとおり異常とせず、警告 CA-P-52 で気づく)。(b)(c) は採らない | FS 固有の目印ファイルの案(CFS-P-24)は採用しない |
| 11 | CM-U-4 | SIGTERM 時の扱い | 実行中のジョブの完了を待たず、終了処理もしない。次回の起動時の回復で `failed`(`crawler_restart`)(実装は CA-P-74、CM-P-35) | 停止の時間予算と `stop_grace_period` の注意は CA-P-74 |
| 12 | CA-U-3 | メンテナンスフラグの書き込み手段 | 運用者の手動手順。Crawler は読み取りのみ | |

承認は仮値(数値)の確定ではない。仮値は architecture 11章と `apps/crawler/README.md` 4章が正本(CA-U-1)。

## 5. 実装者が自律的に決めてよい事項と、決めてはいけない事項

実装は完了している。**実装担当が決めた内容**は各新版に「実装で決めた内容」として記録された。ユーザーの確定でも承認でもなく、変えるときは設計書の改版を提案する(1章の 2)。

**実装で決めた内容(ポインタ。内容は各新版が正本)**:

| 文書 | 新規 ID | 主な内容 |
| --- | --- | --- |
| architecture | CA-P-56〜76 | Store 層の結果区分と例外、応答喪失後のリトライ、読み取りの規則、状態遷移の補足、メンテナンスフラグの確認位置、記録の整理の種別ごとの判定、件数の不変条件の確認位置、終了通知・ポーリング・警告の具体、ソース削除・Scheduler の補足、起動順・停止の時間予算・整合性検査・環境変数名・採用した仮値 |
| crawler-api | CAPI-P-20〜29 | 更新(PUT)の処理順、検証と 400 の細部、`config_invalid` の整形、取り消し・ロック解放の補足、形式不正な設定記録、`/healthz` の実装済みの応答形、本文の上限 10 MiB(CAPI-P-29。仮値。ユーザー指示 2026-11-16)、int64 の範囲外を検証しないこと(CAPI-P-28 (b)。CAPI-U-11 を解消) |
| module | CM-P-28〜37 | `SourceReader`/`SourceStore`、HTTP クライアント(urllib3。CM-U-2 を解消)、`jobs` の入口の公開物、`documents`・`crawl` の決定、`api` の入口、設定、起動・停止、Store 層の契約、機械検査とログ |
| FS | CFS-P-25〜31 | glob の多項式時間の照合、`FsOps`、エンコーディングの確認、`from None`、列挙ストリームの終端、テスト環境の判定、最悪入力の許容 |
| interface | CI-P-18 | 想定外の例外の変換で元の例外を traceback に出さない |

そのほか、設計書が「実装時」に決めるとしていた次は、実装で決まった: 同期 HTTP クライアント(CM-U-2。CM-P-29)、全件走査のタイブレーク(呼び出し側が一意な `document_id` で終える。CA-P-57)とソース削除の順 3 の方式(全件走査 + バルク削除。条件指定の削除は置かない。CA-P-66、CM-P-36)、起動時の整合性検査で読む環境変数名(`LORELEY_CRAWLER_INDEXER_<名前>`。CA-P-75。CM-U-9 は 2026-11-16 のユーザー回答で解消)。仮値は実装が既定値を採用した(CA-P-76、`apps/crawler/README.md` 4章)。

**なお未決**(承認で解消していない。実装者は決めない。決める場所は各新版の未決の表):

| 区分 | ID | 内容・決める場所 |
| --- | --- | --- |
| architecture | CA-U-1 | 数値の正式値(実測後。CM-U-6、CAPI-U-10、CFS-U-6 も同様)。承認は仮値の確定ではない |
| | CA-U-10 | 並行モデル(CM-P-13・14。専用スレッドと専用の Store 層クライアント)は承認済みの案だが、CA-U-10 は ID 列にないので未決のまま。残る論点は、スレッド安全性・ブロッキング I/O 中のハートビートの実機確認(CM-U-1、CFS-U-4)と、Web の `next()` の最大ブロック時間(CM-U-8) |
| | CA-U-12 | Admin API 設計の不在(Admin API 設計時)。「利用者への表示」(PD 9.2 #8。原本サイズ超過・`error_count` の表示)もここで扱う |
| | CA-U-14 の運用部分 | compose で Indexer の上限(と `loreley-jobs` の索引名)を両者に同じ値で渡す定義(infra の別タスク)。Crawler 側の扱い(未設定は警告して検査を省略。環境変数名は `LORELEY_CRAWLER_INDEXER_<Indexer の設定名>`)はユーザー回答で解消(CM-U-9) |
| | CA-U-18 | 実機でしか確認できない項目(下の「実機確認が要る項目」) |
| crawler-api | CAPI-U-5・6・10 | 重複起動の扱い、送信後の取り消しの示し方、HTTP タイムアウトなどの数値 |
| | CAPI-U-3 の残り | `ratio_threshold` の入力単位、Admin 側の既定値(Admin API・Admin View の設計時。`schedule_interval_seconds` の下限・上限は cron 式への置き換えで該当なし) |
| | CAPI-U-1 | Admin API 側の 409 の扱いと Admin API 設計の不在(Admin API 設計時) |
| module | CM-U-1・8 | スレッド安全性・実機確認(CM-U-1)、Web Connector の構成(CM-U-8)。CM-U-3・9 は 2026-11-16 のユーザー回答で解消 |
| FS | CFS-U-4・6 | 実機での確認、数値の正式値と実測 |
| interface | CI-U-3、CI-U-5・7〜11 | CI-U-3 は上限値などの数値(仮値。実測後。`error_count` の定義は決まった)、CI-U-5・7・8(Web 分)・9・10・11 は Web・各 Connector 文書で対応する。CI-U-1・4・6 は 2026-11-16 のユーザー回答で解消(CI-U-2 は承認で解消済み) |
| (解消済み) | architecture・interface・module | 2026-11-16 のユーザー回答で解消した(追補。各新版が正本): CA-U-4(`error_count` は抽出失敗の件数のまま。「利用者への表示」は CA-U-12 に委ねる)、CA-U-5(ジョブ記録は MVP では自動で消さない。運用で手動整理し、自動の整理は後から追加)、CA-U-8(定期起動の周期は cron 式に置き換わった。止まっていた間の分は起動しない。起動の判定の実装・検証の細部・環境変数名は提案)、CA-U-9(テストベクタは Crawler 側だけ。実 Indexer との一致は別タスクの結合テストで確認。CM-U-3・CI-U-1 も同じ)、CA-U-13(回復時に確認結果の区分を書かない)、CA-U-14 の Crawler 側(CM-U-9。未設定は警告して検査を省略) |
| (解消済み。上の続き) | architecture・interface | CA-U-7・CI-U-4 の残り(識別子エラーは警告のみ。管理者が TTL 内に `invalid_id_count` の警告に気づく運用)、CI-U-6(事前確認を置かない。`check_source()` は追加しない) |
| (解消済み。上の続き) | crawler-api | CAPI-U-2(Admin API が `loreley-sources` を直接読む)、CAPI-U-4 の残り(表示名の項目は持たせない)、CAPI-U-7 の残り(ロック解放の保護は現状の実装を承認。`acquired_at` が直近 60 秒(仮値)以内は解放しない)、CAPI-U-8 の残り(移行処理・警告なし) |
| (解消済み。2026-11-16 の追補(0024)) | crawler-api・architecture | CA-U-20(専用の復旧経路を置かず運用で対処)、CAPI-U-11(int64 範囲外は考えない)、CAPI-U-12(本文の上限 10 MiB・仮値。CAPI-P-29)は、2026-11-16 のユーザーの回答で解消した(実装で見つかった未決だったもの) |

**決めてはいけない**: 上の「なお未決」。そのうちユーザー判断が要るもの(CAPI-U-3 の残り(`ratio_threshold` の入力単位・Admin 側の既定値)など)は、案があれば案どおりにし、案がなければ決めずにユーザーへ確認する。運用・設計書の改版時に決める事項(CA-U-14 の運用部分)、Admin API 設計時に決める事項(CA-U-12(CA-U-4 の「利用者への表示」を含む)、CAPI-U-1・3 の残り・5・6)も実装者は決めない。ユーザー未確認の提案(architecture CA-P-77: cron 式の起動の判定の実装・検証の細部・環境変数名 `LORELEY_CRAWLER_TIMEZONE`。crawler-api CAPI-P-30、module-structure CM-P-38)も確定として扱わず、変えるときは設計書の改版を提案する。Crawler はメンテナンス中の応答を承認済みの案(409)で実装し、Admin API 設計時に再確認する(CAPI-U-1)。承認済みの案、実装で決めた内容を変えたい場合は、実装で変えずに設計書の改版を提案する。

**実機確認が要る項目**(単体テストでは確認していない。結合テストは別タスク。一覧と理由は `apps/crawler/README.md` 8章):

- 実 OpenSearch: `create`・`if_seq_no` の原子性、スレッド安全性(CM-U-1)、10,001 件以上の走査・PIT・refresh・バルク削除の部分失敗(architecture 12章 #37)、実環境のソート・絞り込み(CA-U-18)。
- 実 Indexer: Status の項目の出方、`document_id` の照合(CM-U-3。別タスクの結合テストで確認する)、件数照合の独立検証、起動時の整合性検査と上限(12章 #39)、ロック文書を Indexer が実機で読めること(CA-U-18)。
- 実機の FS: マウント外れの errno、`st_ino`、取得中の変更、ブロッキング I/O 中のハートビート(CFS-U-4)。
- 実コンテナ・compose: `/healthz` の `healthy` 化、実行中ジョブがある状態での `docker stop` の所要時間。

**判断に迷うとき**: (1) 設計書に承認済みの案があれば案どおりにする。(2) 案がなく、実装時に決める事項に当たらないなら、決めずにユーザーへ確認する(推測で確定しない)。(3) 案を変える必要が見つかったら、実装で変えず、設計書の改版を提案する。(4) 削除に関わる判断は、安全側(ジョブを `failed` にして削除させない)に倒す(architecture 1.4)。

## 6. 今は決めなくてよい事項

| ID | 内容 | 決める時期 |
| --- | --- | --- |
| I-40、CI-U-11、CW-U-8 | 列挙中の一時失敗が列挙全体の失敗になる(選択肢 (a)〜(d))。MVP(FS)に影響しない | Web の詳細設計の前 |
| I-44 | Indexer の文字コード対応が UTF-8・CP932 のみ。Indexer 側の判断。FS(MVP)にも当てはまり、EUC-JP などは文字化けしうる | Web の実装前。FS(MVP)への影響は残る |
| CW-U-1〜20、CM-U-8、CI-U-5・7 | Web Connector の詳細(URL 正規化、探索、認証、robots など)。Web は MVP の対象外(CW-K-1・2) | Web の詳細設計時 |
| module 7.7 | 複数 Crawler・キュー化(MVP の対象外) | 将来 |

## 7. 既存設計との不整合(I-n)

Indexer・PD・SD は変更していない。定義の場所は architecture 13.5 など。

| ID | 要点 | 定義 |
| --- | --- | --- |
| I-1 | SD はソース削除のロックを途中で消すとするが、Indexer K29 は最後まで保持。K29 に従う | architecture 13.5 |
| I-2・I-3 | SD の突合ジョブ、`loreley-texts` は PD で削除・不採用。Crawler は含めない・依存しない | 同上 |
| I-4 | SD の起動指定に `rewrite_mode` がない。Crawler は追加する | 同上 |
| I-5 | Indexer が仮に置いたロック文書・フラグ・索引名・失敗種別名。Crawler 側は承認済みの案(2026-11-16)。Indexer 設計書側の記述は案のまま | 同上 |
| I-6 | 解消(CA-K-21)。索引・マッピングの作成担当は `opensearch-init` | 同上 |
| I-7 | Indexer README 6章が古い(v0.10 で確定した事項を未決と記載)。Indexer 側の課題 | 同上 |
| I-8 | PD は権限エラーも数回リトライと読めるが、本設計は即スキップ(承認済みの案を維持) | 同上、architecture 6.2 |
| I-10・I-11 | `\` の置換と NFC/NFD による `document_id` の衝突、原本サイズ超過の拒否の記述の食い違い | interface 11.5 |
| I-20 | SD 14.2 の中継操作にソース削除ジョブ起動と設定の登録・更新・削除がない | api 5.5 |
| I-30 | SD の `os.walk` の `onerror` では一部の列挙エラーを検出できない。FS は `os.scandir` の自前走査 | FS 11.5 |
| I-40・I-44 | 6 章のとおり(未決) | Web 4.5 |

I-41・I-42 は interface に反映済み、I-43 は解消済み。I-9・I-50・I-51 は欠番。

## 8. 実装・テストで押さえる異常系

設計が想定する異常系を、テストで再現できるようにする(architecture 12章の番号。#35〜#39 は architecture v0.2、#40〜#43 は architecture v0.4 で追加)。単体テストは fake・スタブで実装済みで、実 OpenSearch・実 Indexer・compose が要るものは結合テスト(別タスク)に持ち越している(5章の「実機確認が要る項目」)。

| # | 異常系 | 確認すること |
| --- | --- | --- |
| 5・6・31 | 終了通知の固定、202 の扱い、`failed` の送信条件 | 再送が同じ内容。202 を受理とせず Status で確認。送信開始後は `failed` を送らない |
| 9・10 | リトライと連続スキップ | 取得失敗と登録失敗の混在、連続 20 件で `failed`、散在は打ち切らない |
| 13 | ロックとハートビート | `create` の原子性、同期 HTTP の待ち中も更新、解放後のハートビートが何も変えない |
| 14・25・30 | 取り消しの各時点と競合 | 終了通知の前は削除されない。送信後は削除が止まらない |
| 15・27・28・29・32 | 再起動の回復とロック解放 | `running` → `failed`(`crawler_restart`)、孤児ロック、リース切れの解放と Job Runner の競合、喪失時にロック文書を削除しない |
| 16・17・34 | ソース削除 | 順 0〜6 の順序、`DELETE` のボディ、途中停止後の再実行、メンテナンスフラグ(承認済みの案) |
| 21・38 | 識別子の例外 | 衝突はジョブ `failed`、識別子エラーが混ざっても件数照合が成り立つ。規則変更で期限削除の対象になりうること |
| 33 | Store 層の書き込み失敗 | リトライを尽くして `failed`(`store_unavailable`) |
| 35 | 設定の 1 回の読み取り | 手順 6 の読み取りの後に設定を更新しても、同じ版の値で進む。`settings_source_updated_at` が一致。設定なし・`deleting` などは `running` から `config_invalid` |
| 36 | 0 件列挙の警告 | 前回 1 件以上・今回 0 件で `warnings` に残る。ジョブの status は変わらない |
| 37 | 10,001 件以上の記録 | 実 OpenSearch で、整理とソース削除がすべての記録を扱い、PIT が閉じる。バルク削除の部分失敗 |
| 39 | 起動時の整合性検査 | Indexer の上限を超える仮値で起動が失敗する。上限ちょうどで通る |
| 40 | 件数の不変条件(CA-P-71) | 不一致のとき整理も `enumeration_completed` も行わず `failed`(`internal_error`)になる。確認は整理の前と送信の前 |
| 41 | メンテナンスフラグの範囲(CA-P-65) | ソース削除は順 1・2・4(各試行の前と待ちの間)だけ確認し、順 0・3・5 では確認しない。順 2 の最中に立っても順 3 は実行され、順 4 の前で `failed`(`maintenance`)になり再実行で完了する |
| 42 | 停止(CA-P-74) | SIGTERM で終了コード 0。実行中のジョブは `running` のまま残り、次回の回復が `failed`(`crawler_restart`)にする |
| 43 | 応答喪失後のリトライ(CA-P-58) | `AlreadyExists`・`Conflict` で読み直し、自分の書き込みなら成功。スキップ記録が二重計上されない |

## 9. Admin View / Admin API を作る際の注意

- **`include_patterns` は「既定拡張子への追加」**(承認済み。CFS-U-1): 一般の glob の「対象を絞る」直感と逆で、`docs/**` を入れると拡張子を問わず全ファイルが対象になる。絞るには `root` を狭めるか `exclude_patterns` を使う。設定画面の表示名・説明文でこれを示す(FS 2.1)。
- 設定の「削除」はソース削除ジョブの起動で、索引済み文書も消える(CA-K-22)。
- `loreley-jobs` の書き込みは Crawler だけで、Admin API は読み取りのみ(確定。CA-K-2)。`loreley-sources` を Admin API が直接読む経路は、ユーザー回答 2026-11-16 で案どおりに決まった(CA-P-46。CAPI-U-2 を解消。Crawler に読み取り API は足さない)。
- しきい値(0 以上 1 未満)の範囲検証は Admin API の担当(CA-K-16)。入力単位(%)の変換は未決(CAPI-U-3)。更新は全置換(承認済み。CAPI-P-7)で、画面が現在値を取得する経路が前提(CAPI-U-3)。
- `connector_type` は登録後に変更できない(承認済み。CAPI-P-9)。`source_id` の文字種は承認済み(CAPI-P-15)。表示名の項目はなく、管理画面は `source_id` を表示する(ユーザー回答 2026-11-16。CAPI-U-4 を解消)。
- 定期起動の周期は `schedule_cron`(cron 式。標準の 5 項目、秒なし。null は手動のみ)で入力する(ユーザー回答 2026-11-16。`schedule_interval_seconds` は廃止)。タイムゾーンは設定項目でなく、Crawler の環境変数で全ソース共通(同じ)。Crawler が止まっていた間に過ぎた時刻は起動されない(同じ)。`@daily` などの別名は受け付けず、400 になる(提案。ユーザー未確認。CAPI-P-30)。
- `external_id` に影響する設定を変えても、移行処理・警告はない(FS 2.4。ユーザー回答 2026-11-16。CAPI-U-8 を解消)。
- 終了通知の送信後は取り消しても削除が止まらない。画面での示し方は未決(CAPI-U-6)。
- `warnings`(0 件列挙の警告)の表示は、crawler-api の応答にはなく、Admin API が `loreley-jobs` を直接読んで出す形で、Admin API の設計で決まる(architecture 2.2、CA-U-12。FS 3.4.1)。リース切れの `failed` 表示の判定方法も CA-U-12。
- メンテナンス中の応答は、Crawler は承認済みの案(409)で実装済み。Admin API 側の扱いは Admin API 設計時に再確認する(CAPI-U-1)。重複起動(`lock_held`)の扱いは Admin API 設計時に決める(CAPI-U-5)。

## 10. 参照

| 文書(`docs/v0.x/system-design/` 配下) | 版 | 内容 |
| --- | --- | --- |
| `crawler/crawler-architecture-v0.4.md` | v0.4 | 責務、データモデル、ジョブ、ロック、リトライ、Indexer 連携、ソース削除。13章に CA-K/P/U、I-n、横断一覧(13.8)、12章にテスト観点 |
| `crawler/crawler-api-v0.4.md` | v0.4 | Admin API → Crawler の契約(CAPI-K/P/U) |
| `crawler/crawler-module-structure-v0.5.md` | v0.5 | Python のモジュール構成、並行モデル、依存ルール(CM-K/P/U) |
| `crawler/connector/connector-interface-v0.3.md` | v0.3 | Connector の抽象、識別子規則、エラー分類(CI-K/P/U) |
| `crawler/connector/connector-file-system-v0.3.md` | v0.3 | FS Connector(MVP)。設定、走査、errno、テスト(CFS-K/P/U) |
| `crawler/connector/connector-web-v0.3.md` | v0.3 | Web Connector の外枠(MVP の対象外。CW-K/P/U)。v0.3 は承認の反映と参照先の更新だけで、CW-U は 1 件も解消していない |
| `indexer/indexer-api-v0.10.md`、`indexer/indexer-architecture-v0.10.md` | v0.10 | Indexer 側の契約と設計(Crawler の前提。変更しない) |

課題の全件(ID・一行要約・参照先)は architecture 13.8。実装は `apps/crawler/`(挙動・環境変数・持ち越しは `apps/crawler/README.md`)。

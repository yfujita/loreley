# Crawler 決定事項(実装着手のための要約)v0.2

- 版: v0.2
- 更新日: 2026-11-13
- 前版: `crawler-design-decisions-v0.1.md`
- v0.2 の改訂: module-structure v0.3 への追従だけ。`connectors` を `infrastructure` の外の独立したモジュールにした(ユーザーの指示。CM-K-10)ことを 2 章の方針 #15 に足し、参照先を v0.3 にした。ほかは参照先の更新(略称・10 章)を除き v0.1 から変更していない。
- 位置づけ: Crawler 設計書 6 本(下の 10 章)の**要約**。実装担当(エージェント)が「何から着手してよいか」「どこまで自律的に決めてよいか」を判断するための短い文書で、詳細は書き写さず、ID と章番号で参照する。
- **この文書は何も決めない**。確定・案・未決を新たに作らず、各設計書の区分をそのまま写す。正本は各設計書で、食い違いがあれば各設計書を正とし、この文書を直す。この文書は ID を持たない。
- 区分は architecture v0.2 冒頭の凡例に合わせる(確定=ユーザー確定、案=ユーザー未確定、未決、推測、導出)。**確定にしてよいのは、各設計書が確定(CA-K など)としているものだけ**。
- 設計書 6 本(v0.2)は、ユーザーの承認前の版である(`agent_tasks/20261113_create_crawler_design/STATUS.md`)。この Crawler 設計でのユーザー回答は、Q1〜Q3 と、2026-11-13 の 3 点(索引・マッピングの作成担当、設定の削除の解釈、`connectors` を独立したモジュールにすること)。ほかに、Indexer 設計書・PD でユーザーが承認済みの事項がある(3章で区別する)。
- 略称: architecture=`crawler-architecture-v0.2.md`、api=`crawler-api-v0.2.md`、module=`crawler-module-structure-v0.3.md`、interface/FS/Web=`connector/` 配下の各 v0.2。章番号は「architecture 7.5」のように書く。Indexer 設計書は「Indexer api」「Indexer arch」と書く(例: 「Indexer api 3.5」は Indexer の API 設計書の章)。

---

## 1. 最初に守ること

1. 案は設計書の案どおりに実装する。ユーザー判断が要る未決を、実装者が確定しない(5章)。
2. 案を変えたいときは、実装で変えずに、設計書の改版(新版ファイル)を提案する。
3. Indexer の設計書・実装は変更しない(この設計タスクも、Crawler の実装タスクも)。Indexer 側の課題は報告に書く。ただし、実装タスクの前提作業として `infra/opensearch/schema/` を変更する(4章)。
4. 未回答の判断を承認扱いにしない。

## 2. 採用している設計方針

| # | 方針 | 区分 | 参照 |
| --- | --- | --- | --- |
| 1 | 責務分担: Connector は列挙・取得だけ。リトライ・スキップ・Indexer 登録・ジョブ管理・ロックは Crawler 本体。Connector は Indexer・ジョブ・ロックを知らず、内部でリトライしない | 案(分担は導出、リトライなしは CI-P-5) | interface 1.4・3.1、architecture 2.2 |
| 2 | 呼び出し順: ロック取得 → 開始通知(列挙前)→ チャンクごとに `last-seen`(取得より前)→ 取得 → バッチ登録 → 全応答を確認して終了通知(202)→ Status API のポーリング | 確定(順序)。チャンクの区切り方は案 | CA-K-3、CA-P-16、architecture 4.5・4.6・7.1 |
| 3 | 削除の判断(割合ルール・件数照合・対象決定)と実行は Indexer だけ。Crawler は検索インデックスと削除記録を書かず、期限による削除も要請しない(ソース削除だけが例外)。読まないことも設計原則とする | 確定(削除の判断と実行は Indexer)。読み取りの禁止は導出 | CA-K-2、architecture 1.4・2.2・8章 |
| 4 | 列挙の完全性と削除安全性: 一部でも列挙できなければ `Completed` にせず失敗にする。マウント外れなど全体の異常では文書を削除しない。終了通知の受理前の失敗は削除しない。迷ったらジョブを `failed` にして削除させない | 完全性・受理前の失敗は確定(CFS-K-4、CA-K-9)。「迷ったら `failed`」は導出 | interface 3.3、architecture 1.4・9章 |
| 5 | ジョブの status と削除結果は切り離す。ポーリングの失敗はジョブの status を変えず、確認結果の区分(`confirmed`/`unconfirmed`/`unknown`)を残す | 確定(切り離し)。区分の名称は案(CA-P-30) | CA-K-4、architecture 7.6 |
| 6 | Indexer に見せる値の固定: 設定スナップショットと終了通知の内容はジョブごとに固定し、再送は同じ値。型は strict | 確定 | CA-K-5・CA-K-6 |
| 7 | 設定の読み取りは 1 回: 手順 6 は `running` への遷移 → `loreley-sources` を 1 度だけ読む(`ttl` 等と `connector_config` を同じ版で確定)→ `settings_snapshot` を追記。設定なし・`deleting`・値の欠落・型違いは `config_invalid`(`running` からの `failed`)。`connector_config` はジョブ記録に保存しない。診断用の読んだ版は、`settings_snapshot` の外の最上位項目 `settings_source_updated_at`(旧名 `config_updated_at` は使わない) | 案 | CA-P-51、architecture 3.2・3.3.1・4.5 |
| 8 | ロックはソース単位。ハートビートはジョブ実行と独立したスレッド(専用の Store 層クライアント)で、同期 HTTP・Connector の呼び出し中も更新する。所有権を失ったら Indexer への要請を止める。リース切れだけでは自動で引き継がない | 案(ソース削除の要件は確定: CA-K-11) | CA-P-2〜9、CM-P-13・14、architecture 5章 |
| 9 | リトライ・スキップ: 失敗の種別ごとに `retry` 属性に従う。`write_conflict`・`update_conflict` はリトライして解消しなければ `failed`(スキップしない)。連続 20 件のスキップで打ち切る | 競合の扱いは確定(CA-K-10。20 は案)。ほかは案 | CA-P-18〜20、architecture 6章 |
| 10 | Store 層は Repository インターフェース経由。`loreley-jobs` の書き込みは Crawler だけ。`loreley-sources` の登録・更新・削除は Crawler が受ける(Admin API は Crawler の口を呼ぶ)。索引・マッピングの作成は `opensearch-init` | 確定 | CA-K-2・CA-K-19・CA-K-21、CM-K-3・CM-K-4・CM-K-9 |
| 11 | Admin API が `loreley-sources` を読み取りのみで直接読む経路(決定は Admin API 設計時) | 案 | CA-P-46、architecture 2.2・2.3 |
| 12 | 0 件列挙の警告と、識別子エラーの削除判定への影響: 観測性と記述の明確化だけで、削除の挙動は変えない(保留・抑止は CA-U-19・CA-U-7 で未決) | 案 | CA-P-52、architecture 7.7 |
| 13 | 10,000 件超の記録の走査・バルク削除(PIT + `search_after`、走査前の refresh)と、Indexer の上限との起動時の整合性検査(Indexer の設定名に対応する値を compose で渡す。Crawler が読む名前は CM-U-9 で未決) | 案 | CA-P-53〜55、architecture 3.1・6.4・10章 |
| 14 | MVP は単一ホスト・単一 Crawler・直列実行(Job Runner が `queued` を 1 件ずつ実行)。実装は Python(Indexer に揃えた構成) | 確定(単一・直列・Python)。構成は案 | CM-K-1・CM-K-8、CA-P-11、CM-P-1・19 |
| 15 | モジュール構成: `connectors` は `infrastructure` の配下に置かず、アプリケーション機能の層の独立したモジュールにする(データソースへの接続のほか、クロール対象の管理など複雑な処理を持つため)。必要があれば `connectors` が `infrastructure` を使う。`infrastructure` は `opensearch`・`indexer_client`。`connectors` が Store 層・Indexer クライアント・他のアプリケーション機能に依存しないことは、interface 1.4 と R5 からの導出(案) | 確定(独立したモジュールにすること、必要があれば `infrastructure` を使うこと。CM-K-10)。ほかは案 | CM-K-10、CM-P-1・7、module 4.10・6章 |

## 3. ユーザー確定事項(実装者が必ず守るもの)

全件は各設計書の「確定」の表を見る。ここは主要なものだけ。

| 確定 | ID | 実装者が守ること |
| --- | --- | --- |
| Q1 | CA-K-19、CAPI-K-1 | crawler-api は Admin API が呼ぶ口だけ(クロール起動、取り消し、ロック解放、設定の登録・更新・削除、ソース削除ジョブ起動)。Crawler → Indexer の呼び出しは architecture に従う |
| Q2 | CI-K-7、CFS-K-3、CA-K-7 | FS は設定の包含・除外で列挙を絞り、既定は対応拡張子。対象外は列挙も `last_seen_at` の要請もせず、`enumerated_count` に数えない。包含パターンは設定で追加できる(意味の確認は CFS-U-1) |
| Q3 | CA-K-20 | 各設計書は末尾に未決・課題を持つ。既存設計との不整合は `I-n`。Indexer 設計書は書き換えない |
| 2026-11-13 | CA-K-21、CM-K-9 | 索引・マッピングは `opensearch-init`(`infra/opensearch/schema/`)が作成・管理する。`loreley-sources` を追加し `loreley-jobs` を拡張する。Indexer が読む 4 項目(`owner`・`job_id`・`lease_expires_at`・`enabled`)の型は維持する。Crawler 側では作らない。個々のマッピング(CA-P-49)は案 |
| 2026-11-13 | CA-K-22、CAPI-K-8 | 設定の「削除」はソース削除ジョブの起動(索引済み文書も削除)。設定だけを消す API・操作は置かない。設定の削除は手順の最後 |
| 2026-11-13 | CM-K-10 | `connectors` は `infrastructure` の配下に置かず、アプリケーション機能の層の独立したモジュールにする。データソースへのアクセスに必要があれば `infrastructure` を使う(ここまでが確定)。`opensearch`・`indexer_client`・他のアプリケーション機能に依存しないことは、interface 1.4 と module R5 からの導出で案 |
| Indexer・PD 由来 | CA-K-1〜6、8〜10 | HTTP で直接通信、呼び出し順、status と削除結果の切り離し、設定スナップショット・終了通知の固定、202 は受理の確認ではない、受理前の失敗は削除しない、競合は `failed` |
| 同上 | CA-K-11・12 | ソース削除はロックを最後まで保持し最後に削除する。リース更新を続け、所有権を失ったら止め、再実行で復旧し、削除中のソースに新しいクロールを起動しない。`DELETE` も `lock` を JSON ボディで送る |
| 同上 | CA-K-13〜18 | ID の検証(空でない・制御文字なし・256 バイト以内)、原本サイズ超過は Crawler と Indexer の両方で拒否、登録結果の集計は Crawler、しきい値の範囲検証は Admin API だけ、`force_delete` は手動実行のみ、Indexer のメンテナンスフラグの読み取りは fail-closed(Crawler 側の読み取りは案。CA-P-34) |
| 同上 | CI-K-1〜6、CFS-K-2・4・5・10 | `document_id` と `external_id` の規則、`content_hash`・孤立サロゲート。FS は読み取り専用マウント、列挙失敗では削除しない、0 件列挙は異常にしない、全件更新 |
| 同上 | CM-K-4〜7 | Repository 経由、`DELETE` のボディ、strict な JSON 型、ソース削除中のリース更新 |

注意: CFS-K-6(権限エラーの扱い)は、リトライしない即スキップが案で、PD と食い違う(I-8)。CA-K-7 の `enumerated_count` の数え方の定義は案。

## 4. 実装着手を妨げる事項(着手前に決める・やるべきこと)

**前提作業**(Crawler の**実装タスク**で行う。CA-K-21、CM-K-9。作成・管理の担当は確定): `infra/opensearch/schema/` に `loreley-sources` の索引定義を追加し、`loreley-jobs`(`jobs.json`)を拡張する(マッピング案は architecture 3.1 の表)。現在 `jobs.json` は 4 項目だけで、`loreley-sources` の定義はない(2026-11-13 に確認)。`jobs.json` は Indexer の結合テストと共有するため、同時に更新する(CA-K-21)。Indexer が読む 4 項目の型は変えない。

加えて(案。architecture 3.1・10章。CA-K-21 の確定範囲は担当まで):

- `infra/opensearch/init-indices.sh` は索引ごとに `create_index_if_absent` を列挙しているので、`loreley-sources` の追加には、`schema/` の定義に加えて、スクリプトへの作成の呼び出しと索引名の環境変数の追加が要る。
- 既存の環境への反映: `create_index_if_absent` は既存の索引を更新しないため、既存の環境には `jobs.json` の拡張が入らない。前提作業に、既存の索引への項目追加(put mapping。`dynamic: false` で足りるかは未確認。CA-U-18)か、開発・検証用の既存ボリュームの作り直しのどちらかを含める。どちらにするかは実装タスクで決める。

**ユーザー判断待ち**(作業記録 `agent_tasks/20261113_create_crawler_design/0009-task-review.md` の「第 2 群(実装前)」。いずれも未回答で、案は確定ではない):

| # | ID | 内容 | 設計書の案・推奨 | 備考 |
| --- | --- | --- | --- | --- |
| 1 | CAPI-U-4、CA-U-15 | `source_id` の文字種 | 案: 半角英数字で始まり、半角英数字・`.`・`_`・`-` だけ(CAPI-P-15) | 後から狭めると互換性の問題(0009) |
| 2 | CFS-U-1 | glob 構文の確定と、`include_patterns` の意味 | 案: glob、既定拡張子への追加。選択肢: 置き換え、名称変更(`additional_include_patterns` など) | 変更は FS の改版と既存設定の見直しになる |
| 3 | CA-U-6、CI-U-2、CFS-U-5 | `external_id` 衝突時の扱い | 案: ジョブ `failed`(CA-P-24)。0009 の推奨: MVP は案を承認し、運用で緩和を検討 | 1 組の衝突でそのソースのクロールと期限削除が止まり続ける |
| 4 | CA-U-2 | 「削除中」の置き場所 | 案: `loreley-sources.status=deleting`(CA-P-35) | 他の候補: ロック文書、ジョブの状態 |
| 5 | CA-U-16 | 連続スキップを取得段階にも広げる | 案: 取得段階と登録段階を別カウンタ(CA-P-20) | Indexer api 3.5・SD v0.8 3.1 にない本設計の独自の拡張 |
| 6 | CA-U-17 | ソース削除中のメンテナンスフラグ確認 | 案: 順 1・2・4 の送信前に確認し、立っていれば `failed`(`maintenance`) | Indexer arch 11章の開始前チェックに `source_delete` が含まれない点も確認事項 |
| 7 | CAPI-U-3、CAPI-U-8、CAPI-U-1 | 設定項目の必須・更新の全置換、`connector_type` の変更不可、メンテナンス中の応答(409 か 503) | 案: 必須・既定値なし・全置換(CAPI-P-7)、変更不可(CAPI-P-9)、409(CAPI-P-4。crawler-api が返す) | CAPI-U-1 の決める場所は Admin API 設計時(0009 は第 2 群に含めた)。Crawler は 409 の案で実装する |
| 8 | CA-U-7、CA-U-4 | 識別子エラー文書のジョブ status と記録、原本サイズ超過の記録先・status への影響 | 案: `partially_succeeded`(CA-P-25)、別記録・status に影響なし(CA-P-23) | CA-U-7 には「1 件でも削除を抑止する」選択肢が追加された(新規の挙動。確定扱いにしない) |
| 9 | CFS-U-2、CFS-U-3 | `follow_symlinks`・`include_hidden` の初期値、`title` の取得元 | 案: 両方 `false`、ファイル名のみ | |
| 10 | CA-U-19、CFS-U-7 | 0 件列挙のときの削除の保留(v0.2 で追加) | 案(a): 現状維持(PD 5.2 のとおり異常とせず、警告 CA-P-52 で気づく。推奨) | (b) は PD v0.19 5.2 との関係の確認が要る。(c) は FS 固有の目印ファイル(CFS-P-24)で、Web には効かず運用の手間が増える。0009 に載っていない新規の未決 |

0009 の推奨・案どおりに着手する場合も、ユーザーの回答が出るまでは未確定として扱い、変更が入っても差し替えやすい局所的な実装にとどめる。後から変えるコストについて、#1 は 0009 が、後から狭めると互換性の問題になると指摘している。#2 は CFS-U-1 が、変更は FS の改版と既存設定の見直しになると書いている。

## 5. 実装者が自律的に決めてよい事項と、決めてはいけない事項

**決めてよい**(設計書が「実装時」「実測後」「実機確認」で決めるとしているもの。決めたら作業記録に残す):

| ID | 内容 |
| --- | --- |
| CA-U-1、CM-U-6、CFS-U-6、CAPI-U-10 | 数値(リース、バッチ、タイムアウト、ポーリング間隔など)は、仮値・設定可能で実装し、実測後に正式値を決める |
| CA-U-18、CFS-U-4、CM-U-1 | OpenSearch の `create`・`if_seq_no`、PIT・`search_after`、ロック文書の相互読み取り、スレッド安全性、FS の errno などの実機確認 |
| CM-U-2 | 同期 HTTP クライアントのライブラリ(`DELETE` のボディ・API ごとのタイムアウト・スレッド使用ができること) |
| CM-U-9、CA-P-55 | 起動時の整合性検査(案を出発点)で Crawler が読む環境変数の名前と、未設定のときの扱い(compose の定義と合わせる) |
| CA-P-49 | マッピングは architecture 3.1 の案を出発点に調整してよい(`dynamic` の設定を含む)。Indexer が読む 4 項目の型は変えない(CA-K-21) |
| CA-P-53、CA-P-54 | 案を出発点に、細部だけ実装時に決める: 全件走査のタイブレーク(実機確認後。keyword 項目 `document_id` が第一候補。全件走査は `record_type` ごとに 1 回ずつ行う。同じソースの `skip` と `oversize` が同じ `document_id` で共存しうるため。1 種類の中では記録の ID により `document_id` が一意。architecture 3.1)、ソース削除の順 3 の方式(条件指定の削除か、一覧 → バルク削除) |
| module 7.7 | モジュール内部のファイル名など |

**決めてはいけない**: 設計書が「ユーザー判断」を決める場所にしている未決(例: CA-U-2〜8、13、15〜17、19、CAPI-U-3・4・7・8、CFS-U-1〜3・5・7、CM-U-3 の Indexer 側)。CM-U-4(SIGTERM 時の扱い)は、決める場所が「ユーザー判断(運用)・実装時」の二重のため、案(実行中のジョブの完了を待たない。次回の起動時の回復で `failed`)どおりに実装し、判断を待つ。運用・設計書の改版時に決める事項(CA-U-14、CM-U-5・CAPI-U-9)も実装者は決めない。0009 の第 3 群は「実装時までユーザー判断を待てる」の意味で、実装者が決めてよいという意味ではない(例: CA-U-3 のメンテナンスフラグの書き込み手段、CA-U-8 の周期形式は、案どおりに実装しユーザー判断を待つ)。Admin API 設計時に決める事項(CA-U-12、CAPI-U-1・2・5・6)は、Admin API の設計で決める(Crawler の実装者は決めない)。メンテナンス中の応答(CAPI-U-1)は、Crawler は案(409)で実装し、Admin API 設計時に再確認する。

**判断に迷うとき**: (1) 設計書に案があれば案どおりにする。(2) 案がなく、実装時に決める事項に当たらないなら、決めずにユーザーへ確認する(推測で確定しない)。(3) 案を変える必要が見つかったら、実装で変えず、設計書の改版を提案する。(4) 削除に関わる判断は、安全側(ジョブを `failed` にして削除させない)に倒す(architecture 1.4)。

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
| I-5 | Indexer が仮に置いたロック文書・フラグ・索引名・失敗種別名。承認までは案 | 同上 |
| I-6 | 解消(CA-K-21)。索引・マッピングの作成担当は `opensearch-init` | 同上 |
| I-7 | Indexer README 6章が古い(v0.10 で確定した事項を未決と記載)。Indexer 側の課題 | 同上 |
| I-8 | PD は権限エラーも数回リトライと読めるが、本設計は即スキップ(案を維持) | 同上、architecture 6.2 |
| I-10・I-11 | `\` の置換と NFC/NFD による `document_id` の衝突、原本サイズ超過の拒否の記述の食い違い | interface 11.5 |
| I-20 | SD 14.2 の中継操作にソース削除ジョブ起動と設定の登録・更新・削除がない | api 5.5 |
| I-30 | SD の `os.walk` の `onerror` では一部の列挙エラーを検出できない。FS は `os.scandir` の自前走査 | FS 11.5 |
| I-40・I-44 | 6 章のとおり(未決) | Web 4.5 |

I-41・I-42 は interface に反映済み、I-43 は解消済み。I-9・I-50・I-51 は欠番。

## 8. 実装・テストで押さえる異常系

設計が想定する異常系を、統合テストで再現できるようにする(architecture 12章の番号。#35〜#39 は v0.2 で追加)。Indexer との連携は、OpenSearch と実 Indexer を compose で起動して確認する。

| # | 異常系 | 確認すること |
| --- | --- | --- |
| 5・6・31 | 終了通知の固定、202 の扱い、`failed` の送信条件 | 再送が同じ内容。202 を受理とせず Status で確認。送信開始後は `failed` を送らない |
| 9・10 | リトライと連続スキップ | 取得失敗と登録失敗の混在、連続 20 件で `failed`、散在は打ち切らない |
| 13 | ロックとハートビート | `create` の原子性、同期 HTTP の待ち中も更新、解放後のハートビートが何も変えない |
| 14・25・30 | 取り消しの各時点と競合 | 終了通知の前は削除されない。送信後は削除が止まらない |
| 15・27・28・29・32 | 再起動の回復とロック解放 | `running` → `failed`(`crawler_restart`)、孤児ロック、リース切れの解放と Job Runner の競合、喪失時にロック文書を削除しない |
| 16・17・34 | ソース削除 | 順 0〜6 の順序、`DELETE` のボディ、途中停止後の再実行、メンテナンスフラグ(案) |
| 21・38 | 識別子の例外 | 衝突はジョブ `failed`、識別子エラーが混ざっても件数照合が成り立つ。規則変更で期限削除の対象になりうること |
| 33 | Store 層の書き込み失敗 | リトライを尽くして `failed`(`store_unavailable`) |
| 35 | 設定の 1 回の読み取り | 手順 6 の読み取りの後に設定を更新しても、同じ版の値で進む。`settings_source_updated_at` が一致。設定なし・`deleting` などは `running` から `config_invalid` |
| 36 | 0 件列挙の警告 | 前回 1 件以上・今回 0 件で `warnings` に残る。ジョブの status は変わらない |
| 37 | 10,001 件以上の記録 | 実 OpenSearch で、整理とソース削除がすべての記録を扱い、PIT が閉じる。バルク削除の部分失敗 |
| 39 | 起動時の整合性検査 | Indexer の上限を超える仮値で起動が失敗する。上限ちょうどで通る |

## 9. Admin View / Admin API を作る際の注意

- **`include_patterns` は「既定拡張子への追加」**: 一般の glob の「対象を絞る」直感と逆で、`docs/**` を入れると拡張子を問わず全ファイルが対象になる。絞るには `root` を狭めるか `exclude_patterns` を使う。設定画面の表示名・説明文でこれを示すのが FS 2.1 の案。追加か置き換えか、名称変更かはユーザー未確定(CFS-U-1)。
- 設定の「削除」はソース削除ジョブの起動で、索引済み文書も消える(CA-K-22)。
- `loreley-jobs` の書き込みは Crawler だけで、Admin API は読み取りのみ(確定。CA-K-2)。`loreley-sources` を Admin API が直接読む経路は案(CA-P-46、CAPI-U-2)。
- しきい値(0 以上 1 未満)の範囲検証は Admin API の担当(CA-K-16)。入力単位(%)の変換は未決(CAPI-U-3)。更新は全置換が案で、画面が現在値を取得する経路が前提(CAPI-U-3)。
- `connector_type` は登録後に変更できない(案。CAPI-P-9、CAPI-U-8)。`source_id` の文字種は案(CAPI-P-15)。
- 終了通知の送信後は取り消しても削除が止まらない。画面での示し方は未決(CAPI-U-6)。
- `warnings`(0 件列挙の警告)の表示は、crawler-api の応答にはなく、Admin API が `loreley-jobs` を直接読んで出す形で、Admin API の設計で決まる(architecture 2.2、CA-U-12。FS 3.4.1)。リース切れの `failed` 表示の判定方法も CA-U-12。
- メンテナンス中の応答(409 か 503)は、Crawler は案(409)で実装し、Admin API 設計時に再確認する(CAPI-U-1)。重複起動(`lock_held`)の扱いは Admin API 設計時に決める(CAPI-U-5)。

## 10. 参照

| 文書(`docs/v0.x/system-design/` 配下) | 版 | 内容 |
| --- | --- | --- |
| `crawler/crawler-architecture-v0.2.md` | v0.2 | 責務、データモデル、ジョブ、ロック、リトライ、Indexer 連携、ソース削除。13章に CA-K/P/U、I-n、横断一覧(13.8)、12章にテスト観点 |
| `crawler/crawler-api-v0.2.md` | v0.2 | Admin API → Crawler の契約(CAPI-K/P/U) |
| `crawler/crawler-module-structure-v0.3.md` | v0.3 | Python のモジュール構成、並行モデル(CM-K/P/U) |
| `crawler/connector/connector-interface-v0.2.md` | v0.2 | Connector の抽象、識別子規則、エラー分類(CI-K/P/U) |
| `crawler/connector/connector-file-system-v0.2.md` | v0.2 | FS Connector(MVP)。設定、走査、errno、テスト(CFS-K/P/U) |
| `crawler/connector/connector-web-v0.2.md` | v0.2 | Web Connector の外枠(MVP の対象外。CW-K/P/U) |
| `indexer/indexer-api-v0.10.md`、`indexer/indexer-architecture-v0.10.md` | v0.10 | Indexer 側の契約と設計(Crawler の前提。変更しない) |

課題の全件(ID・一行要約・参照先)は architecture 13.8。

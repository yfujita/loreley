# 0005 crawler-api / connector-file-system / connector-web 作成(P3)とR3レビュー

- 日付: 2026-11-13
- 実施: P3(document-writer 3名並列)、R3(document-reviewer 3名。各文書とも初回+差分確認。FS は初回のみでメインが反映を確認)
- 結果: 3文書とも R3 通過(Critical 0。Important は api 4件・Web 5件・FS 4件をすべて反映。軽微指摘も反映済み)

## 成果物(いずれも新規)

- `docs/v0.x/system-design/crawler/crawler-api-v0.1.md`
- `docs/v0.x/system-design/crawler/connector/connector-file-system-v0.1.md`(約680行)
- `docs/v0.x/system-design/crawler/connector/connector-web-v0.1.md`

## crawler-api

- API は6本(案): クロール起動 / ソース削除起動 / 取り消し / ロック解放 / 設定の登録 / 設定の更新。読み取りAPI・設定の直接削除APIは置かない(Admin API が `loreley-jobs` を直接読む。設定レコードを消すのはソース削除ジョブの手順5だけ)。
- Q1「設定の削除」と「ソース削除ジョブ起動」を同一操作とする解釈は案(CAPI-P-11)。K29 の順序から事実上強制される解釈だが、ユーザー未確認のため CAPI-K-1 では「削除の実現方法は案」と書き分けた。承認時に確認する。
- R3 の主な指摘と反映: ①「ソース削除の受付で `status=deleting` を許す」を確定と書いていた(architecture 8.3 は案)→案に分離 ②`job_id` が `record_type=job` 以外の記録に当たりうる→`record_type=job` のみジョブとみなし他は404 ③更新の反映境界(`queued`→`running` の遷移)と取り消しの判定順(`job_not_found`→`job_not_cancellable`→`job_already_finished`→200/202) ④受付途中ロックの誤解放防止(`acquired_at` が直近なら `lock_in_use`)、`reason` 6値の定義、冪等比較規則、孤児ロック判定条件の絞り込み。
- 採番: CAPI-K-1〜7、CAPI-P-1〜18、CAPI-U-1〜10、I-20(SD v0.8 14.2 の Admin API 中継一覧にソース削除起動・設定の登録・更新・削除がない)。
- Admin API 設計書が存在しないため、契約を先行定義(CAPI-U-1、CA-U-12 と対応)。

## connector-file-system

- 設定項目5つ(案): `root`(必須)、`include_patterns`(既定拡張子への追加)、`exclude_patterns`、`follow_symlinks`(既定 false)、`include_hidden`(既定 false)。未知キーは拒否。glob は `*`・`?`・`**` のみ(隣接する `**` は `config_invalid`)。適用順は 隠し→種別→除外→包含(除外優先)。
- 実機確認(Python 3.12/3.13): `os.walk` は `is_dir()` の `OSError` を握りつぶし、`glob`・`pathlib.rglob` も例外を握りつぶす → I-30(SD v0.8 3.1 の「`os.walk` + `onerror`」では不十分)。
- 0件は失敗にしない(PD 5.2 確定。保護は Indexer の割合ルール・TTL)。`size_hint` は返さず、`open`(`O_NONBLOCK` 付き)→`fstat`→読む前に上限判定→読み取り→再`fstat` で変更検出。`create` でルート確認。マウント外れは errno で分類(`source_not_found` / `source_unreachable` / `enumeration_incomplete`)。`title`=ファイル名(NFC)、`source_updated_at`=mtime(範囲外は固定値)、MIME対応外は `application/octet-stream`。
- R3 の Important: ①疑似コードがメモリ見積もりと矛盾(サブディレクトリの一覧を先読み)→`pop` 時に `read_dir` ②glob の `**` 連続で変換が一意に決まらない→隣接 `**` を無効に ③FIFO で `os.open` がブロック→`O_NONBLOCK`+`fstat` ④管理者向けエラー説明(errno・パス)を載せる経路が architecture の `failure_detail`(固定文)にない→他文書への修正要望に統合。
- 採番: CFS-K-1〜10、CFS-P-1〜22、CFS-U-1〜6、I-30。

## connector-web(概要)

- 結論: interface の構造(列挙/取得の分離、ストリーミング、識別子規則、エラー分類、`fetch(ref, max_bytes)`、設定の扱い)は Web でも成立し、要素を変える確定的な齟齬はない。ただし契約の設計判断が必要な点(I-40)と文言補足(I-41・I-42)、MVPにも影響する矛盾(I-43)がある。
- 修正要望(Web文書での記録): **I-40**(Connector 内リトライなし+列挙 `Failed` はリトライされないため、Web では一時的な 5xx・429 が1件あるだけで列挙全体が失敗する。選択肢 (a) interface 3.1/CI-P-5 の方針変更 (b) EnumerationStream の再開契約 (c) architecture 6.2 の方針変更 (d) 現状維持=大規模サイトでほぼ完了しない(推測)。Web 詳細設計の前に判断が必要、MVP 影響なし)/**I-41**(「存在し続けた文書は必ず返す」の補足。低)/**I-42**(契約テスト #8 と訪問済み集合・frontier。低)/**I-43**(architecture 7.7 の「`locator` の表示用文字列」と interface 3.2 の `locator` 不透明規定が矛盾。MVP(FS)にも影響、緊急度高)/**I-44**(Indexer の文字コード対応が UTF-8・CP932 のみ。Web で顕在化する既存制約で FS にも当てはまる。Indexer 設計は変更しない)。
- 採番: CW-K-1〜5(引用元つき)、CW-P-1〜6、CW-U-1〜20、I-40〜I-44。論点の列挙に留め、Web の具体方式・値は決めていない。

## P4 で反映する他文書への修正要望(統合版)

**architecture(R2通過済み。v0.1 を直接修正)**
- 5.3: ジョブ記録の書き手の整理。「ジョブ記録は別の実行単位だけが書く」は、受付が保存する `queued` 記録(4.3 手順5)、`queued` の取り消し(4.7)、管理者のロック解放による `running`→`failed` と矛盾する。API側が条件付き更新で書く記録を整理(高。module-structure の前に)
- 4.7: 取り消し要求を Job Runner に伝える方式(単一 Crawler のメモリ上のフラグなど)。リース切れ `running` への取り消しの扱い(高)
- 7.7: I-43。`warnings` の表示用文字列は、`locator` ではなく規則適用前の `external_id` の切り詰めを使う(秘密情報は CW-U-17 の除去が前提)、または件数と分類名だけにする(高)
- 3.3.1・4.8: 列挙失敗・`create` 失敗の `failure_detail` に、分類名に加えて Connector の説明文(固定文+errno名+切り詰めた相対パス)を載せてよいと定める。`external_id_collision` の `failure_detail` に衝突2件のパスを載せる(中)
- 3.3: `job_id` で取得した記録の `record_type` 確認(中)
- 2.2・2.3: Admin API が `loreley-sources` を読む経路の明記(CAPI-U-2。中)
- 5.1: `acquired_at` の意味(create 時に必ず設定、ハートビートでは更新しない)。5.4: `queued` ロックの扱い(低)
- 3.2・4.5: `connector_config` の確定時点(手順8。スナップショットに含まれず手順6と8の間の更新が反映されうる)の明記(低)
- 9章: 「マウント切れ(FS)」行に FS 3.3 への参照(低)。13.7・3.2: CA-U-15 の案として CAPI-P-15 を置いたことの反映(低)
- 13.8 横断一覧: CAPI-U-1〜10、I-20、CFS-U-1〜6、I-30、CW-U-1〜20、I-40〜I-44 の追記

**interface(R1通過済み。v0.1 を直接修正)**
- 11.5: I-1〜I-6 の参照を architecture 13.5 に差し替える
- 6.1: ConnectorError の説明文の定義を、固定文に加え errno名・切り詰めた相対パスを含めてよいものに緩和(architecture 3.3.1・4.8 と整合)
- 9章: 結論を Web 文書 4.1 の差し替え文(案)に改訂する(構造は成立/I-40 は契約の設計判断/I-41・I-42 は補足)
- 3.3 の 2(I-41)、10章 #8(I-42): 文言・テスト観点の補足(低)

## 未対応事項・ユーザー判断候補(設計書内では案・未決・I-n として記録済み。承認時にまとめて確認)

- I-40(Web 列挙中の一時失敗の扱い。Web 詳細設計の前。MVP影響なし)
- Q1「設定の削除」の解釈(CAPI-P-11)、`ttl` 等の必須・更新は全置換(CAPI-U-3)、`source_id` の文字種(CAPI-P-15)、`connector_type` 変更不可(CAPI-U-8)、メンテナンス中は 409(CAPI-U-1)
- glob 構文の確定(CFS-U-1。`include_patterns` が「追加」か「置き換え」かを含む)、symlink・隠しファイルの初期値(CFS-U-2)、`title` を内容から取るか(CFS-U-3)、衝突1組でソース全体がジョブ `failed` になる影響(CFS-U-5、CA-U-6)
- 次: P4(architecture・interface の修正と横断一覧の完成)→ P5(crawler-module-structure。R5)。

# 0010 R1 レビュー結果(A・B)

日付: 2026-11-22
レビュアー: document-reviewer(メインが記録)

## 結論

Critical なし。Important 7 件、Suggestion 17 件、Nitpick 5 件。既存設計(crawler-api 3・4章、SD、機能設計、画面仕様)への写像は概ね正確で、推測の混入は確認されなかった。`git diff --stat 2cb500fa` は空(tracked ファイルは無変更)。未追跡は `agent_tasks/…`、`docs/v0.x/system-design/api/`、`docs/v0.x/system-design/ui-admin/frontend/` のみ。

## 確認できた点(要旨)

- crawler-api との照合: 6 API の写像(パス・ステータス・本文)、code、`details`、`existing_job` と番兵値、判定順序、接続前の失敗・回復中は正確
- SD §7.2・§7.3・§14.4・§6.1〜6.4、PD §6.1 の引用は実物と一致。SD §14.4 の逸脱と §7.3 の緩和は記録済み
- 索引スキーマ(`infra/opensearch/schema/*.json`)に B が使うフィールド・型が揃っている。未マップ項目への依存なし
- A↔B の整合(章番号・EP 番号・ID 参照、2.3 の code 表 14 種と各 EP のエラー表、EP-01〜14 と見出し)。不採用項目の残存は記録のみ
- AF-1〜20、画面データ項目の検算は実際の画面仕様と一致
- 安全性(認証なしの破壊的操作、`root` の任意パス、127.0.0.1 publish、OpenAPI 既定無効、エラー本文に値・パスを出さない)は A 2.3・B 2.10 に明記
- 技術事実: FastAPI `app.frontend()` は 0.138.0 で追加(公式リリースノート)、依存の版は `pyproject.toml` と一致

## Important(7件)

1. **I-1 `job_id` は「エンコードが要らない文字種」ではない**(B 9.1・2.12、A 5.3): `job_id` の検証が「空でない・256 バイト以内・制御文字なし」だけで `%`・`?`・`#`・`..` が通り、Crawler URL に埋めるとパスが崩れる(固定経路の主張に反する)。修正案: (a) `job_id` を安全な文字種に絞る、または (b) Crawler 呼び出し時に全文字をパーセントエンコード(`safe=''`)と明記し、9.1 の記述を訂正
2. **I-2 `config_invalid` 分解で `connector_config.connector_config` になる**(B 2.5): FS Connector は項目名が `connector_config` 自身の違反(「オブジェクトでない」「未知の項目がある」。`apps/crawler/.../filesystem/config.py` の 60・64 行、connector-file-system v0.3)を出す。修正案: 前半が `connector_config` ならプレフィックスなしで `field=connector_config`。`detail` が日本語固定文である点を AAPI-U-2 に併記
3. **I-3 「`config_invalid` が 404・409 より先」は 404 について誤り**(B 3.4・9.2.5): 実際の処理は、設定があり種別が読めるときだけ検証し、なければ検証せず 404。先に返りうるのは 409 `source_deleting` に対してだけ。crawler-api 側の文言の曖昧さは申し送り候補
4. **I-4 ゲート2の「不採用」(複数選択の未選択という解釈)がユーザーの明示判断として書かれている**(A 2.3・冒頭・BAPI-P-15・BAPI-U-8、B 2.10・冒頭・AAPI-P-15・11.7 の #19・#23): リスク受容をユーザー判断に帰属させている。修正案: 「ゲート2の回答で採用が選ばれなかったため不採用として扱った(解釈。ゲート3で確認)」「リスクを受容するかはゲート3で確認する」に書き換え
5. **I-5 `-K-` の出典・区分に疑義**: (a) AAPI-K-9 の更新間隔 30 秒・外部リンクの出典は機能設計 AF-18・20 ではなく画面仕様 dashboard #26(ゲート C)・admin-view 3章(ゲート B)。出典を訂正 (b) BAPI-K-6・AAPI-K-9 の時刻 ISO 8601 UTC は CA-P-38(承認済みの案)で、ユーザー確認が不明 (c) AAPI-K-6 はゲート1 #4 の承認そのもの→「承認済みの案」、AAPI-K-5 は回答は明示だが方式のみと注記 (d) BAPI-K-3 のユーザー確定は「Indexer・Crawler と揃える」まで。個別選定は pyproject からの導出→区分を「導出」に
6. **I-6 本文規約の矛盾**(B 2.12 と 4.1): 「EP-03・04・06 は Content-Type: application/json 必須(違反は 400)」と「EP-06 は本文なし・`{}` を同じとして扱う」が衝突。加えて Content-Type 厳格化は text/plain の単純リクエストをふさぐが、本文なしの POST(EP-05 ソース削除ジョブ、EP-06、EP-07)は保護されない。修正案: 本文が空なら Content-Type を問わず許すと明記。A 2.3 の BAPI-U-8 に露出する EP を列挙(EP-05 全文書削除、EP-06 `force_delete` 既定 false、EP-07 取消。DNS rebinding なら全 EP)。軽い緩和(全 POST で Content-Type 必須など)を足すかは要件外のため**ユーザー確認**
7. **I-7 EP-02 の JSON 例が仕様と矛盾**(B 3.2): ジョブ記録を取れなかった部分失敗の例なのに `lock.state=lease_expired` と `lock.job.*` が埋まっている(`lease_expired` は `status=running` をジョブ記録から読む必要。ロック文書も `loreley-jobs` 索引内)。修正案: 別の失敗パターン(検索インデックス失敗で `index.document_count=null`+`unavailable`)に差し替え

## Suggestion(17件。要旨)

S-1 `unavailable` のキー規則の揺れ(`stalled` は `last_crawl.stalled` 等の正式パスに。行ごとの失敗は行内の null で決まる)/ S-2 `lock_state` の `orphan` と `just_acquired` の重なり、ジョブ `status` が読めないときの値(`unknown`)を排他的に定義 / S-3 EP-13 のトップ `checked_at` の定義と例、`id` の説明(`web` は compose のサービスではない)/ S-4 EP-12 の例の内部矛盾 / S-5 `ratio_threshold_percent` の応答が小数第 2 位を超えうる(Crawler 直登録値)→再保存で `format` エラー。注意書き・十進数変換の明記 / S-6 `ttl` の範囲(1 以上。ゲート1の「非負」からの変更)を記録しゲート3で承認 / S-7 `reason=read_only` は未使用(削除、または PUT の `source_id`・`connector_type` を `read_only` に)/ S-8 A 5.6 の「最悪約 93 秒」の出典・導出表記 / S-9 `stalled` 偽陽性回避のため C への引き継ぎに「ロック→ジョブの順で読む」/ S-10 `ExistingJob.lease_expires_at` の番兵値と `null` の使い分け(EP-02 の `lock.job`)/ S-11 D1 の `opensearch` 確認が 3 秒・再試行なしであることを A 5.6 に / S-12 SSRF の観点(確認先 URL は環境変数のみ、プローブはリダイレクトに従わない・3xx は `unexpected_status`)/ S-13 AF-5 と機能設計の記述の差を I-n・HO に / S-14 AF-U-1・3・5・6・7・9・10・13 の「決めた/案/後続」表 / S-15 J1 の「開始」列の並べ替え対応を一文で / S-16 B 2.6 の 1 行目と 2 行目の `source_id` の重なり / S-17 ゲート3の対象の明示(A に一覧、B 11.9 に AAPI-P-3)

## Nitpick

B 11.7 #23 の正本列「A 5.5」→「なし(A 2.3)」/ 同一 job_id が例ごとに別状態 / 「・」前の空白 / A 5.3 の検証順序にクエリがない / `HO-n` はフェーズ5で実番号に置換し、R4 で残存がないことを確認

## ユーザー確認事項(R1 から。ゲート3まで保留または質問)

1. #19・#23 を不採用とした解釈でよいか。A 2.3 のリスク受容を明示判断として記載してよいか(I-4)
2. 0001 の「既存設計でそのまま使うもの」(更新間隔 30 秒、ISO 8601 UTC ほか)はユーザー確認済みか。AAPI-K-5・K-6 を `-K-` のままにするか(I-5)
3. `ttl` の範囲(1 以上)をゲート1「非負」からの変更として承認するか(S-6)
4. 本文なし POST への軽い緩和を要件に足すか(I-6)

## メインの対応方針

- 1・2・4・5・6(仕様部分)・7、およびほぼ全 Suggestion・Nitpick は、文書の修正(表記・整合・誤りの訂正)として writer に依頼する。区分は安全側(確定→承認済みの案・導出、不採用→「扱った(解釈)」)に直す
- ユーザー確認事項 1〜4 は、文書では「ゲート3で確認」と明記し、ゲート3で質問する(I-6 の緩和は要件にない追加なので足さない)
- 修正後に reviewer が差分を再確認 → 解消なら C・F に進む
- C への引き継ぎに S-2・S-9・S-12 を追加

## 次

- writer(B の担当)に A・B の修正を依頼 → 再レビュー(R1 再確認)→ C・D、F

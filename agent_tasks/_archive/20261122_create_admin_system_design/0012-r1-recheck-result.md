# 0012 R1 再確認の結果

日付: 2026-11-22
レビュアー: document-reviewer(メインが記録)

## 結論

R1 の Important I-1〜I-7 はすべて解消。Critical・新たな Important の事実誤りは N-1 を除きなし。他文書は無変更(`git diff --stat 2cb500fa` は空。未追跡は `agent_tasks/…`、`docs/v0.x/system-design/api/`、`docs/v0.x/system-design/ui-admin/frontend/` のみ)。A 328 行・B 1323 行。表・フェンス・JSON(A 1、B 16)に崩れなし。C へ進んでよい。F は E が B の変更に追従した後。

## 解消確認(要点)

- I-1: 全文字パーセントエンコード(B 2.12・9.1、A 5.3、11.10)。crawler-api 3.3 の `%2F`→404 `not_found`、`%3F`・`%25`・`%2e%2e`→400 と一致。実機未確認は AAPI-U-12
- I-2: `field="connector_config"` の例外が `connectors/filesystem/config.py` 60・64 行、FS v0.3、`patterns.py` 39 行の文言と一致
- I-3・I-7: 訂正済み / I-4: 「不採用として扱った(解釈。ゲート3で確認)」に A・B 全箇所で統一。「ユーザーが明示的にリスクを受け入れたわけではない」と明記 / I-5: 欠番と移動先の対応が一貫(N-3 参照)/ I-6: 矛盾解消(N-1 参照)
- Suggestion S-1〜S-17・Nitpick は反映済み(`read_only` は Crawler 由来の写像行のみ残存=意図どおり。AF-U の表は AF-U-1・3・5・6・7・9・10・13 を網羅)

## 新規指摘(writer に修正依頼済み)

- **N-1(Important。事実誤り)**: 「単純なリクエストで届きうる EP」に EP-08(DELETE)を含めたのは誤り。CORS の単純なリクエストは GET・HEAD・POST のみ。クロスサイトの DELETE(EP-08)・PUT(EP-04)は preflight 対象。届くのは本文なし POST の EP-05・06・07、EP-08 は DNS rebinding のみ。対象: A 2.3・BAPI-U-8、B 2.10
- N-2(Suggestion): `unavailable` のキー表記が `items[]` 付き正式パスになっていない箇所(B 3.1 EP-01 表、6.1 の `existence`、AAPI-P-30、11.9 の AAPI-P-25)
- N-3(Suggestion): `-K-` の基準の不統一。AAPI-K-9 を承認済みの案(画面仕様ゲート B・C)へ、BAPI-P-20 の凡例説明を追加、AAPI-P-7 に「`ttl` 下限を除く(P-37)」の注記
- N-4(Suggestion): 「単一プロセス」の出典を「導出(Crawler・Indexer も単一プロセス)」に
- N-5(Suggestion): `%`・`?` を含む `job_id` は Admin の検証を通り Crawler が 400/404 を返し得て 502 になる。EP-07 では 404 `job_not_found` に写す案(新規 AAPI-P-39。ゲート3)
- Nitpick: B 11.9 の AAPI-U-12 重複、A 5.6 の「約 93 秒」の出典表記(10章の「最大約 90 秒」と 11章の値からの導出)

## 次の進め方(reviewer 提案)

- N-1〜N-5 は軽微な修正。再レビューは差分確認で足りる
- C は N-1 の訂正を待たず着手可。ただし C への引き継ぎに N-2 のパス規則と N-5 の `job_id` 写像を足す
- N-3 は区分の扱いにユーザー判断が要る箇所もあるので、ゲート3に積む
- F は E の追従後

## 確認できなかったこと

Crawler の `%3F`・`%25` の実 uvicorn での挙動(AAPI-U-12)、E 側の追従状況(0011 に記載済み)

## 次

- writer の N-1〜N-5 修正 → 結果を作業記録に残す
- C → D(document-writer)。E の追従完了後に F

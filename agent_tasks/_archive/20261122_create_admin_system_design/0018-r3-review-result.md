# 0018 R3 レビュー結果(E・F)

日付: 2026-11-22
レビュアー: document-reviewer(メインが記録)

## 結論

Critical なし。Important 10 件、Suggestion 10 件、Nitpick 8 件。E・F は DS・admin-view・画面仕様・A・B との突き合わせで致命的な矛盾なし。「軽微な修正で可」。フェーズ5へは Important 1〜6 を直してから進めるのが安全、7〜10 は統合中でも可(メインの判断: すべてフェーズ5前に直す)。他文書は無変更(`git diff --stat 2cb500fa` は空。未追跡は `agent_tasks/…`、`docs/v0.x/system-design/api/`、`docs/v0.x/system-design/ui-admin/frontend/` のみ)。

## 確認できた点

DS 4.1〜4.20 の全部品の置き場が F 3.6 で決定 / E 12.6 の引き継ぎが F 8.6 で全件割り当て / B 2.3 の全 code(Admin 固有 14+共通 6)、`details.errors[].reason` 8 値、`unavailable` 正式パス、`job_already_finished` の成功扱い、`crawler_response_lost` の再送、AAPI-P-39 の 404 が E と一致 / 画面×EP 対応は F 4.1 と B 1.3 が一致 / 欠番 ID の参照なし / route・テンプレート4型・`navGroups`・`data-testid`・URL↔API の対応・invalidate 表・更新間隔が DS・画面仕様と一致 / 技術事実は 0004 と一致

## Important(10 件)

1. **F の I-104・8.7 と E 12.6 が陳腐化**(0017 で解消済みなのに未解消のように記載。F 8.5・8.7・4.1 冒頭、E 12.6): I-104 を削除または「解消済み(0017)」、F 4.1 の記載を「9 画面+シェルで一致」に、F 8.7 の E・B への修正依頼を撤回、E 12.6 を更新
2. **FMOD-K-1 の確定範囲が広すぎる**(DS 4 章の「案」を含む。4.15 の具体値と 4.18〜4.20 は案): FARC-K-5 と同じ範囲(4.5・4.8・5.3・6章)に絞り、残りは「案(DS の区分に従う)」と注記
3. **`-K-` と `-P-` の境界不統一**(FARC-K-5・K-7、FMOD-K-1 が確定、FARC-P-31 は承認済みの案): R1 の基準(DS・画面仕様のゲート B/C の承認事項の引用は承認済みの案、出典を区分欄に書く)に統一(推奨)。K に残すのは FARC-K-1(ユーザー決定)・K-3(ユーザー了承)・K-4(ユーザー回答)・K-8(0001)・K-9(DS 0.1 の前提)、FMOD-K-2〜4。FARC-K-9 の「外部通信なし」は DS 前提4(外部フォント・CDN を使わない)の範囲に。FARC-K-7 は DS 4.9/#36 の「ブラウザと Crawler のタイムゾーンが異なる場合の表示は未決」に触れる
4. **E 5.4 見出しの区分と 12.3 FARC-P-8 の食い違い**: ゲート1・2で承認されたのは TanStack Vue Query の採用のみ。5.4 見出しを「案(FARC-P-8。ライブラリの採用はゲート1で承認済みの案)」に。FARC-P-4 の区分欄を整理
5. **孤児ロック・取得直後の `lock_held` の導線が J2 で行き止まり**(E 6.3、F 5.1 手順4): `orphan`・`just_acquired` はジョブ記録がない場合があり、`existing_job.job_id` があっても EP-10 が 404 になる。画面仕様では孤児ロックの解放入口は S2 のみ(sources 1.5、admin-view 4.1 の DLG-5)。E 6.3 に「`existing_job.status=null` のときの遷移先は J2 ではなく S2(ロック状態カード)。`just_acquired` は「ジョブを表示」を出さない」と明記し、F 5.1 も合わせ、画面仕様(admin-view 7.7)との差を I-n に挙げる(**ゲート3でユーザー確認**)
6. **F の層規則 R7 とテンプレートの責務が矛盾(2点)**(F 3.7・R7・3.6 の 4.5): (a) `PageHeader` にパンくず(`shell/AppBreadcrumbs`、層4)を持たせると `templates`→`shell` の禁止に反する→パンくずをスロットで受ける、または `AppBreadcrumbs` を `components` に移す (b) `templates` が生の `error` の `error.code` を判定するには `admin/api` の import が要り R7 が禁止→`features` の composable が `describeError` で `viewState`(`loading|empty|error|notfound|stale` 等)を作り、`templates` はそれだけを props で受ける
7. **`featureFlag` の担当が E・F で食い違い、DS 5.3 とも差**(E 4.5・4.2、F 1.2・3.7): ナビの描画除外はガードの仕事ではない。外部リンク項目は route を持たない(admin-view 4.2)。`featureFlag` の評価を `SideNav`/`ExternalLinks`(`queries/meta` 利用)に一本化し `beforeEach` から外す、外部リンク項目の定義の置き場を決める、DS 5.3(「ナビとルートを隠す」)との差を I-n に(**ゲート3でユーザー確認**)
8. **E 6.3 の `config_invalid` フォールバックで `crawler_message` の表示が未決定**: 上部アラートに `details.crawler_message`(固定文)をそのまま出す(sources 2.4)。6.4 の「想定外の応答です」は `invalid_request` などに限る
9. **S2・J2 のロック状態カードで `lock.state` 7 値と画面 6 種+取得失敗の対応表がない**(`unknown`・`just_acquired`・`held_crawl` で `queued` の扱い): E 5.7 または 6.x に写像表を足し、F 3.5 に `lockStateView.ts` 等の置き場
10. **`refetchOnMount` の扱いが「手動のみ」の説明と食い違う**(E 5.4・5.5): 「ポーリングなし・フォーカス/再接続での再取得なし。マウント時(画面を開く・戻る)は再取得する」と明記、または `refetchOnMount: false` を J1・X1・O1・S1 に付ける案と比較して決める

## Suggestion(要旨)

11 F 3.4 の表でパイプが崩れている(F 205 行。`\|` にする)/ 12 F 3.6 の「列の省略(カード幅)」が DS 4.3 の区別を落としている(カード幅は J1 のみ。S1・X1 は viewport 基準)/ 13 F 5.4 手順4 の再実行の出し分けが jobs 2.3 と食い違う(`superseded`・`stalled` は無効+理由、それ以外 false は出さない、`null` は出さない+補足)/ 14 R9 の記述が不正確(`describeError` は `admin/api/errors/`)、6章と 7.1 の `tests/` の扱いを統一、R13 に `createVuetify` 呼び出し箇所を / 15 Node の許容範囲が Node 25 を含む(22.18 以上の 22 系、24 系、26 以上)/ 16 ルート遅延読み込みをしない根拠(FMOD-P-17)を追記 / 17 E 5.3 のタイムアウトと `retry` の組み合わせ(`timeout` を再試行対象から外す、または複数読み取り EP で 45 秒超の注記)/ 18 E 6.3 の `retryable=true` の一般則に 6.5 保存系の例外注記 / 19 E 12.3 冒頭にゲート3の確認対象である旨 / 20 E 5.7 D1 の長いセルを箇条書きに

## Nitpick(要旨)

N-1 E 0・1 章の F・C が「作成予定」のまま / N-2 行数の記載が現状と合わない(「R1 修正後」と書く)/ N-3 E 2.1 の「承認済み(DS 10.1。FARC-K-1)」は凡例にない区分名 / N-4 F の I-n 範囲の説明が E の凡例の予約範囲と表記違い / N-5 F 3.6 の「(4.4 の表)」は E 4.4、F 8.6 末尾のスペース / N-6 E 6.6 の「red のアラート」が不明 / N-7 F 3.1 の `tokens.ts` が DS 3.4 の `line-strong`・`ink` に触れていない / N-8 E 10.2 の `vite preview` 4173 と `baseURL` 5173

## ユーザー確認が必要な点(ゲート3に積む)

1. DS・画面仕様のゲート B/C 承認事項の引用の区分(承認済みの案に寄せる方針で直す。ユーザーの承認を取る)
2. 孤児ロック・取得直後の導線を S2 にする(admin-view 7.7 の既承認事項からの逸脱)
3. `featureFlag` の扱い(DS 5.3 との差)
4. ルート遅延読み込みをしない(実測前に決めてよいか)

## メインの対応方針

E・F の担当 writer に Important 1〜10・Suggestion 11〜20・Nitpick を依頼(迷うものは対応せず報告)。区分は R1 の基準(承認済みの案に寄せる)に統一。ユーザー判断が要る点(Important 5・7、Suggestion 16)は文書に案・I-n として明記し、ゲート3で質問する。修正後に差分を再確認。

## 次

writer の修正 → R3 再確認。C 完成待ち → D → R2 → フェーズ5

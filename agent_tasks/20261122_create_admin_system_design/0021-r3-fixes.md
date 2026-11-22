# 0021 R3 指摘の修正(E・F)

日付: 2026-11-22
担当: document-writer(E/F 担当。メインが記録)

## 変更ファイル

- E: `ui-admin-frontend-architecture-v0.1.md`(814 行)
- F: `ui-admin-frontend-module-structure-v0.1.md`(682 行)
- A・B・DS・画面仕様・agent_tasks は無変更。対応しなかった指摘なし。設計判断が変わるもの(Important 5・7、Suggestion 16)は案・I-n・FMOD-U として明記しゲート3の対象にした

## 指摘ごとの対応(要旨)

- Important 1: F の I-104 を「解消済み(0017)」、F 4.1・3.9 更新、F 8.7 の E・B への修正依頼を撤回、E 12.6 に解消済みを明記
- Important 2・3(区分統一): E の FARC-K-5・K-7 を欠番にし **FARC-P-32(DS 規約の引用)・FARC-P-33(ローカル時刻表示の引用)**(承認済みの案。ユーザー確認はゲート3)へ。F の FMOD-K-1 を欠番にし **FMOD-P-26** へ。FARC-K-9 は DS 前提 2〜4・6 の範囲に絞り、E 2.1 の区分名を凡例の「確定(DS 10.1 の引用)」に。K に残るのは FARC-K-1・3・4・8・9、FMOD-K-2〜4
- Important 4: E 5.4 見出しを「案(FARC-P-8。ライブラリの採用はゲート1で承認済みの案(FARC-P-30))」、FARC-P-4(Vuetify exact と TS 6.x は確定、Hey API exact は承認済みの案、その他は案)・P-8 の区分欄を整理
- Important 5: E 6.3 の `lock_held` を `lock_state` 別に書き直し、`existing_job.status=null` のとき「ジョブを表示」を出さず S2 のロック状態カードへ、`just_acquired` は「ジョブを表示」を出さない。F 5.1 手順 4・3.8 も合わせ、**FARC-P-35・I-88(admin-view 7.7 の既承認事項からの逸脱。ゲート3でユーザー確認)**
- Important 6: (a) パンくずは `AppShell` が `useBreadcrumbs` で作って provide し `PageHeader` が inject、`PageBreadcrumbs` は `components`(FMOD-P-28)(b) `features` の composable が `useViewState` で `viewState` を作り `templates` は props だけ(FMOD-P-27)。F 3.7・3.6・R7・1.2・構成図、E 4.4・6.2 を反映
- Important 7: `featureFlag` の評価を `SideNav` と外部リンク領域に一本化し `beforeEach` から外す。外部リンク項目は `shell/externalLinks.ts`(FMOD-P-29)。DS 5.3 との差を **I-89**(ゲート3でユーザー確認)
- Important 8: `config_invalid` のフォールバックは上部アラートに `details.crawler_message` をそのまま出す。6.4 の「想定外の応答です」は `invalid_request` などに限定
- Important 9: E に 5.10 を新設(**FARC-P-34**)。`lock.state` 7 値+取得失敗を画面 6 種に対応づけ(`held_crawl` の `queued`、`just_acquired`、`unknown` を含む)。F 3.5 の置き場 `admin/lib/lockStateView.ts`(FMOD-P-30)。S2・J2・DLG-1 が共有
- Important 10: 「手動のみ」=定期更新とフォーカス復帰の自動再取得をしない意と明記。マウント時(画面を開く・戻る)は再取得。`refetchOnMount: false` は採らない(戻る操作で古い一覧が最新の状態を隠さないため)。F 3.4・4.1 も合わせた
- Suggestion 11〜20 と Nitpick N-1〜N-8 は全件反映(F 3.4 のパイプ修正、J1 のみカード幅・S1/X1 は viewport 基準、再実行の出し分けを jobs 2.3 に合わせる、R9・`tests/` の扱い(R2・R3 のみ適用)・`createVuetify` の置き場(R13)・R16 新設、Node の範囲=22.18 以上の 22 系・24 系・26 以上、遅延読み込みをしない根拠+実測=FMOD-U-11、`timeout` を再試行対象外+複数読み取り EP の注記、保存系の `retryable` 例外注記、E 12.3 冒頭にゲート3の対象、D1 の長いセルを箇条書き、ほか)

## 新規・変更 ID

- E: FARC-K-5・K-7 欠番(→P-32・P-33)、K は 1・3・4・8・9。P-32・P-33(承認済みの案(引用))、P-34(ロック状態の写像。案)、P-35(ロック導線を S2 へ。案。ゲート3)、FARC-U-19(ブラウザと Crawler のタイムゾーンが異なる場合の表示。未決。DS 4.9)、I-88・I-89(新規)、I-87 拡張(S2 の `unknown`)。P-4・P-8・P-18 の区分欄・本文を更新
- F: FMOD-K-1 欠番(→P-26)、K は 2〜4。P-26(承認済みの案(引用))、P-27〜30(案)、FMOD-U-11、P-8・9・17・18 更新、R16 追加(R1〜R16)。I-104 解消済み

## ゲート3の確認事項の増減

- 増: I-88(孤児ロック等の導線を S2 に)、I-89(`featureFlag`)、FMOD-P-17(ルート遅延読み込みをしない)、区分の移動(FARC-P-32・33・30・31、FMOD-P-26)、FARC-U-19
- 減: なし

## 自己検算(writer)

ID 参照の未定義・未参照なし、欠番 ID は欠番行・移動の経緯のみ、表の列数・フェンス整合、E・F の EP は EP-01〜14 のみで code 名は B と一致、E 5.7 と F 4.1 の画面ごとの EP が一致(D1=EP-13 のみ、S3=EP-14 のみ、シェル=EP-14)

## 未対応・次

- R3 再確認は未実施。さらに B の最新の変更(0020: `null` を許す型・`rerun_blocked_reason` の `source_missing`)への E・F の追従が必要 → 担当 writer に依頼後、R3 再確認
- 推測として明記: Vue Query v5 の `isLoading`、Playwright の時計操作、compose の `additional_contexts` 対応版、ブラウザの URL 正規化が `%2e%2e` を `..` とすること

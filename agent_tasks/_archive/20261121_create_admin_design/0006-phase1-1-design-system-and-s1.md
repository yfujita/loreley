# 0006 フェーズ1.1: design-system・シェル・S1 の作成

日付: 2026-11-21 / 実施: web-ui-designer(報告をメインが要約して保存)

## 成果物(すべて新規・v0.1。すべて「案」でゲートB前)

- `docs/v0.x/ui-design/design-system-v0.1.md`(609行): 美的方向性3案比較、トークン(コントラスト実測値併記)、Vuetify 対応表、共通コンポーネント規約、シェルと route `meta`、テンプレート4型、レスポンシブ、a11y、`data-testid`、技術スタック(案)と SD/PD 差分、Search View 流用方針
- `docs/v0.x/ui-design/admin-view-v0.1.md`(428行): 情報設計、ナビ、画面一覧(D1/S1〜S4/J1/J2/X1/O1、ダイアログ DLG-1〜5)、遷移、AF-1〜20 トレーサビリティ(S1確定範囲と第2段階範囲を区別)、危険度の段階、S1 完全仕様、拡張ガイド骨子、案の一覧
- `docs/v0.x/ui-design/mockups/design-system-v0.1.html`(663行)、`mockups/admin-sources-v0.1.html`(830行)。状態アンカー: `#state-normal/empty/error/stale/loading/menu/snackbar`、ダイアログ `#dlg-crawl/-force/-rewrite`、`#dlg-reject-lock/-stale/-maint/-deleting`、`#dlg-delete/-match`、`#dlg-rerun/-unlock/-cancel`
- スクリーンショット(Git管理外 `.playwright-cli/`、約126枚): `admin-sources-{1280|1024|768|375}-*.png`、`design-system-*`

## メインの検証

- `git status`: 変更は `docs/v0.x/ui-design/`(新規)と `agent_tasks/20261121_create_admin_design/` のみ(`apps/`・PD・SD 無変更)
- モックの外部通信: `https?://`・`@import`・`<link`・`src=` の grep 0件

## ユーザー承認が必要な判断(ゲートB。推奨案)

1. 美的方向性: 案A「静かな帳簿」(灰青の地・墨色文字・primary `#1D5B87`。状態は色・形・文言の3つで示す)。B(Material標準寄り)は既定 warning/info が白地で 2.37/3.12 とコントラスト不足、C(コンソール調)はライトのみ前提と相性が悪い
2. トークン: 色(primary `#1D5B87`、独自 `*-container` 色)、角丸 2/4/8px、影は浮かせる要素のみ
3. ナビ: 5項目+設定時のみ OpenSearch Dashboards 外部リンク。グループは区切り線のみ。デスクトップにグローバルヘッダーなし(ページ見出し領域が担う)
4. シェル・テンプレート4型・route `meta`(`title`/`template`/`parent`/`nav`)・共通コンポーネント規約
5. 危険度の段階(実質4水準: 通常/要確認・標準/要確認・警告つき(影響警告枠+確認チェック必須)/要入力確認)。割当: クロール起動(指定なし)・取消・再実行(指定なし)=標準、強制削除・`rewrite_mode`・ロック解放=警告つき、データソース削除=要入力確認。推奨は強制削除・再書き込みを要入力確認にしない(代替: 要入力確認)
6. AF-U-7: 強制削除・`rewrite_mode` は起動ダイアログ内のチェックボックスで指定、オンで警告枠と確認チェックが開く。実行ボタン色: 強制削除=赤、`rewrite_mode`・ロック解放=琥珀。`rewrite_mode` の準備案内は「要約を有効にしている場合は…」の条件付き文言
7. AF-U-3(a): 起動拒否・指定無視はスナックバーを使わずダイアログ内の消えない `role="alert"`。指定が反映されなかった旨を太字。`lock_held`(error)、リース切れ(warning・ロック解放へ案内)、メンテナンス中(error)、削除中(error)で出し分け
8. データソース削除: `source_id` 完全一致(前後空白無視・大文字小文字区別)で実行ボタン有効、初期フォーカスは入力欄、`persistent`
9. 技術スタック: Vuetify 4.3.4 構成(SD §7.5・PD §9.2 #5 との差分と経緯を記載、追従改訂は別タスク)
10. ユーザー未確認の導出の「案」注記: 失敗(リース切れ・ロック未解放)/失敗(ロック解放済み)のタグ、「判定不能」タグ(D1で本格化)、AF-8 起動時指定表示(J2で本格化)

## designer が置いた仮定・調整点

- ブレークポイントは Vuetify v4 値に合わせ、1145px 以上でサイドバー常時、未満は上部バー+ドロワー、840px 未満は表をカード積み、600px 未満はタップ領域 44px。結果、1024px はドロワー、1280px のみ常時サイドバー。社内で 1024px 幅の利用が多ければ常時表示の閾値を下げる調整がありうる
- S1「最終クロール」列は AF-U-9 未決のため「直近クロールジョブの状態と日時」とし並べ替えなし
- S1 は件数が少ない前提でクライアント側 `VDataTable`(案)。ジョブ・文書一覧は `VDataTableServer`。Admin API 設計で要確認
- 削除失敗行には「削除を再実行」(要確認・標準)。実行中の削除行は操作なし
- 日時はブラウザのローカル時刻、cron の解釈タイムゾーンは説明文に明示(取得経路 AF-U-13 未決)

## 未解決・留意

- 実機 Vuetify v4 での確認は未了(行高/`density`、`VAlert` 左帯色 props、`elevation` 対応、`defaults` マージ結果は実装時に確認。仕様書に「未確認」と明記)
- `@mdi/js`(Apache-2.0)の社内ポリシー上の扱い
- Admin API 未設計に依存: 登録文書数・リース切れ判定・cron タイムゾーン取得経路(AF-U-6/13)、S1 のページング方式
- ダッシュボードから他画面への導線(D1 で決める)、再実行ダイアログの引き継ぎ指定は読み取り専用で示す案(第2段階で確定)
- designer の playwright-cli は `file:` を既定で拒否したため、scratchpad 内の設定ファイル(`allowUnrestrictedFileAccess`)で起動(リポジトリには残していない)

## 次のアクション

1. フェーズ1.2: web-ui-reviewer による軽量レビュー(`design-system-v0.1.html`・`admin-sources-v0.1.html`。メインが HTTP サーバーを起動)
2. Critical/Important は designer に差し戻し
3. ゲートB: 上記1〜10 を項目ごとに提示し承認・変更・保留を得る

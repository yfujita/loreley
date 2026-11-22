# 0016 フェーズ3-2: F(フロントエンドモジュール構成)の完成

日付: 2026-11-22
担当: document-writer(E 担当。メインが記録)

## 変更ファイル

`docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.1.md`(669 行。新規。F のみ変更。E・A・B・SD・PD・DS・画面仕様・CLAUDE.md・apps/・agent_tasks は無変更)。C には依存していない(B を参照)。

## 構成

冒頭(版・凡例・ID 体系・関連文書)/ 1 概要(モジュール表)/ 2 構成(2.1 ディレクトリ構成、2.2 層と依存の向き、2.3 Search View との境界、2.4 ルート直下の設定ファイル)/ 3 モジュール詳細(3.1 `shared/theme`、3.2 `shared/ui`・`shared/api`・`shared/lib`、3.3 `admin/api`(パスエンコードの案)、3.4 `admin/queries`、3.5 定義表・共通ロジックの置き場、3.6 DS 共通コンポーネントの置き場(全件)、3.7 templates・shell、3.8 dialogs、3.9 features(D1・S1〜S4・J1・J2・X1・O1))/ 4 画面→route→ページ→composable→EP の対応表(4.1 画面別、4.2 操作別)/ 5 主要シナリオ 5 本 / 6 依存ルール(R1〜R15)/ 7 テスト構成 / 8 確認状況(8.6 に E 12.6 の割り当て表、E・B への修正依頼)

## ID

- FMOD-K-1〜4(確定。既承認文書の引用のみ): route `meta`・テンプレート 4 型・DS 4章の共通部品(DS ゲート B・C)、Vuetify 4.3.4・TypeScript 6.x・`@mdi/js`・自前ナビ(DS 10.1)、ロール・ラベル基準+必要箇所のみ `data-testid`(DS 0.1 前提 6)、同一オリジンの静的配信・Search View は設計しない(BAPI-K-2)
- FMOD-P-1〜25(案。ゲート3で承認を取る): P-1 ディレクトリ構成(`src/shared/`=Search View と共有できる層、`src/admin/`、`tests/`。`apps/web/` 自体は承認済みの案 BAPI-P-11)、P-2 共有層の範囲、P-4 パスエンコードを `admin/api` 層で保証し契約テストで検証(FARC-U-18 への案)、P-5 `queries` の置き場、P-6 エラー変換表、P-7 DS 共通部品の置き場の規則、P-10 DLG-1〜5 は `admin/dialogs/`、P-14 `unavailable` を引く関数、P-15 番兵日時の判定、P-16 S3・S4 共有のフォーム、P-17 ルートは遅延読み込みしない、P-18 依存ルール R1〜R15、P-19・20 テストの配置とフィクスチャ、P-21 `data-testid` は部品の `testid` props でルート要素に、P-24 ファイル命名、P-25 ルート直下の設定ファイル ほか
- FMOD-U-1〜10(未決・実装時確認): ESLint `no-restricted-imports` で R1〜R15 を表せるか、生成 SDK のパスエンコード、Hey API 生成物の構成と公開口、`VDataTable`・`VDataTableServer` の差の吸収、`ConfirmDialog` のフォーカス規則、`ShardMatrix` の列数テスト、共有層の見直し、実 API スモークの置き場、`.`・`..` だけの ID の扱い(推測)、動的 `meta.title` の実装
- I-100〜104: `PageHeader` に DS で部品名の定義がない、DS 4.15 の部品群に独立した節・部品名の一覧がない、注記ブロックが DS 4 章に未定義、確認ダイアログに部品名がない(DLG-5 は S2 と J2 の両方から開く)、**I-104: B 1.3 と E 5.7 は D1 が EP-14 を使うとするが D1 の画面仕様に使う項目がない**

## E・B への修正依頼(F から)

- E 5.7 の D1 の行から EP-14(`['meta']`)を外し、D1 の画面は EP-13 のみ(EP-14 はシェルが取得)。任意で E 12.6 の F への引き継ぎが F 8.6 で全件割り当て済みである旨を追記
- B 1.3 の D1 の行の EP-14 の用途を確認し不要なら外す(軽微)

## 申し送り候補(A 9章へ)

DS の追記候補: `PageHeader`・注記ブロック・確認ダイアログの部品名(I-100・102・103)、`ShardMatrix` の部品群の名前(I-101)。その他は E に従う。実装時確認事項: FMOD-U-1〜10

## 自己検算(writer)

9 画面+シェルが 4.1 の対応表に載り B 1.3 の EP と一致(D1 の EP-14 のみ I-104)、操作 7 種(EP-03〜08)は 4.2、EP は EP-01〜14 のみ、使用 code 名は B と一致、DS 4.1〜4.20 の全部品と shell・templates・注記ブロックの置き場が 3.6 で決定、E 12.6 の引き継ぎと 0013・0015 の追加分は 8.6 で全件割り当て、ID 参照の未定義・未参照なし

## 未対応・ゲート3

- R3(E・F)は未実施。推測 1 点: ブラウザの URL 正規化が `%2e%2e` を `..` として扱うこと(3.3)
- ゲート3: FMOD-P 全般(特に P-17 遅延読み込みしない、P-4 パスエンコードの保証層、P-10 dialogs の置き場)、FMOD-K 4 件、FARC-P-30・FARC-K-5・K-7 の区分

## 次

- I-104 の修正(E・B)→ R3(E・F)。C 執筆中 → D → R2 → フェーズ5

# 0039 システムデザイン v0.6 の作成(「同期」の用語を外す)

## 概要

0038 のプラン(2026-11-08 ユーザー承認、識別子は推奨案の「改名」を選択)に基づき、`docs/v0.x/system-design/system-design-v0.6.md` を v0.5 のコピーから作成した。実施は document-writer、レビューは document-reviewer(1回)と task-reviewer(1回)。v0.5 以前の SD と v0.10 以前の PD は無変更(mtime で確認。内容ハッシュは未取得)。

## 変更ファイル

- 新規: `docs/v0.x/system-design/system-design-v0.6.md`
- 修正: `docs/v0.x/product-design/product-design-v0.11.md`(用語集「旧用語との対応」節を SD v0.6 に合わせて更新、l.8 の関連文書を SD v0.6 に更新)
- 作業記録 0038、本記録(0039)

## 反映内容

- 識別子の改名: `loreley-sync`→`loreley-deletions`、`/syncs/*`→`/crawls/*`(`/crawls/start`、`/crawls/{crawl_id}`、`/crawls/{crawl_id}/finish`)、`syncresult-*`→`deletion_result-*`、`sync-{source_id}`→`deletion-{source_id}`。
- 用語: Sync Manager・同期管理→Deletion Manager・削除管理(§3.9)、同期結果→削除結果、同期状態→クロール状態。Indexer は「文書の登録・更新・削除を担当するサービス」。
- §12.5: 登録結果の保持場所・項目を未決として追加(PD §9.2 #12 と対応)。
- 冒頭: 変更点要約、旧用語との対応表、改訂履歴。過去版の記述は v0.6 の名称で書き、当時の名称を括弧書きで添えた。
- 残した語: 「非同期」「ACL同期」、技術用語の「同期HTTP」「同期応答」(応答を待つ呼び出しの意味で別語。用語集に明記)。
- 仕様は変えていない。

## レビュー

- document-reviewer: Critical なし、Important 2(PD の対応表が SD v0.6 と食い違う、過去版の記述に当時なかった名称)、Suggestion 3、Nitpick 1。全件反映。
- task-reviewer: Critical なし、Important 1(PD l.8 の関連文書が SD v0.4 のまま。v0.10 からの状態)、Minor 3。l.8 は本記録の作成時に SD v0.6 へ更新済み。再レビューは未実施。

## 判断・設計上の理由

- 識別子は実装前なので改名した(推奨案をユーザーが選択)。
- PD v0.11 の対応表更新と l.8 の更新は、PD v0.11 が直接修正中の版であることと、SD v0.6 が前提になったことによる最小修正。

## 未対応事項(次にやること)

- 登録結果の保持場所・項目(PD §9.2 #12 / SD §12.5)。
- 「最終クロール完了日時」に当たる SD の項目の確認(`list_sources` の最終クロール時刻が近い。PD・SD の両方に未確認と記載)。
- 「同期HTTP」系の語を言い換えるかの判断(現状は別語として残している)。
- 過去版・PD のハッシュ照合(今回は mtime のみ)。
- 0035・0037 から持ち越し: 原本サイズ超過時の既存索引の扱い(PD §9.2 #8)、SD の確認状態の更新、ほか 0031 の項目。
- 未コミット(コミットはユーザー指示待ち)。

# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了
- 最終更新: 2026-11-21
- 最新作業記録: 0008-apply-user-confirmations.md

## 現在の状況

成果物 `docs/v0.x/system-design/ui-admin/ui-admin-functions-v0.1.md`(AF-1〜32。MVP は AF-1〜20、将来拡張は AF-21〜32)を作成した。ユーザー確認事項(0007 で挙げた6項目+追加2件)はすべて回答済みで、成果物の UC-8〜UC-17 に反映した(0008)。`CLAUDE.md` の参照先に ui-admin を追記した。document-reviewer 3回、task-reviewer 1回で Critical なし。最後の反映(再レビュー指摘の注意書き・確度表記)は再々レビューを省略(理由は 0008)。成果物・`CLAUDE.md`・作業記録は未コミット(`.claude/agents/requirements-clarifier.md` の変更は本タスクとは別。コミット時に分離する)。

## 次のアクション

1. 必要ならコミット・PR(ユーザーの指示で実施)
2. 後続タスク: PD 追従改訂(4点)、Admin API 設計、UI デザイン

## 未解決事項

- ユーザー未確認の導出: AF-8 で起動時の指定(force_delete・rewrite_mode)を表示する(新機能ID なし)
- ユーザー未確認の前提: AF-P-1〜4(メンテナンス表示のみ等)
- Loreley ダッシュボードの死活情報の取得経路(SD §7.3「api は indexer に接続しない」、`/healthz` は Admin API 契約外)→ 後続の Admin API 設計(AF-U-1)
- PD v0.19 への追従改訂が必要(4点。別タスク)
- 無視通知の方式、「停止中」表示、ダッシュボード更新間隔、要約の failed 遷移・再実行手段、強制削除・再実行・rewrite_mode の確認操作(AF-U-3/4/7)→ 後続設計
- 成果物が crawler-api の挙動を再掲している箇所の整理、作業記録番号の引用の置き換え(後続設計または v0.2)

## ユーザー判断待ち

- なし(確認済み。上記「未解決事項」のユーザー未確認の導出・前提は完了報告で共有)

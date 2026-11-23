# タスク状態

## 基本情報

- 状態: done
- 現在工程: 完了(ユーザーへの確認事項あり)
- 最終更新: 2026-11-23
- 最新作業記録: 0008-address-pr17-review.md

## 現在の状況

HO-51 の追従改訂を完了した。A・B・C・D を改訂し、HO-51 を「対応済み」にした。`apps/` の変更なし(`git diff --stat c0b6e40 -- apps/` は空)。document-reviewer は 2 回(0005・0006)、task-reviewer は 1 回(0007)実施し、Critical・Important はすべて解消した。PR #17 を作成済み(ブランチ `feature/update-api-design-after-base-impl`)。外部レビュー(Suggestion 2 件: `no-store` の担当、`main` だけが機能を知るという表現)に対応した(0008)。

## 次のアクション

1. ユーザーが「ユーザー判断待ち」の確認事項を確認する
2. PR #17 のレビュー・マージ
3. admin 実装タスクで、設計書(D 4.12(b)・A 10.4 の BAPI-U-2)を前提にする

## 未解決事項

- 範囲外で残すもの(詳細は 0007): E・F の「HO-1〜HO-50」表記、HO-39 の状態の見直し、BAPI-U-2 の残り(サブアプリへの `FastAPI(root_path=…)`・入れ子のマウント・OpenAPI の `servers`・`paths`。admin 実装時)、`ClientDisconnect` の挙動
- mermaid 図(D 2.1・5.9)は目視確認のみ

## ユーザー判断待ち

- `apps/api/README.md` 冒頭の「D を追従改訂するまでは実装を正とする」が古くなった。直すか(`apps/` の変更になるので別タスクにするか)
- E・F の「HO-1〜HO-50」を HO-51 に揃えるか(別タスクにするか)
- BAPI-U-2 に未検証 2 点を足した(P-d より広げた)判断でよいか
- D 冒頭の関連 HO を 4 件(HO-39・HO-48・HO-49・HO-51)に広げた判断でよいか
- 0000 が「下書き」のまま(ユーザー記載のため未変更)。確定版に直すか

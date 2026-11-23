# 0008 PR #17 のレビュー指摘への対応

作成: 2026-11-23(メインエージェント)

## レビュー内容

外部レビュー(PR #17)。Critical・Important なし、Suggestion 2 件。マージ可の判断。

## 確認と対応

| 指摘 | 確認 | 対応 |
| --- | --- | --- |
| [Suggestion 1] `no-store` の担当が実装と異なる(設計書はサブアプリ側の `install_common_http(log_access=False)` が担当と書いている) | **妥当**。`create_app(mounts=[SubAppMount("/api/admin/v1", sub)])` で `/api/admin/v1/items` を呼び、`CommonHttpMiddleware.dispatch` が `get_route_path` で見るパスを確認した。外側は `/api/admin/v1/items`(`/api/` で始まる)、サブアプリ側は `/items`(始まらない)。応答の `cache-control: no-store` は外側が付けている(サブアプリ側の middleware は付けない)。実装は変更しない。挙動は問題ないが、責務の記述が不正確だった(0003 で writer が HO-51 内訳の記述をそのまま写していた) | D 4.2・AAM-K-5・AAM-P-23 を「サブアプリ側は例外の吸収(統一エラー形式)を担当し、`/api/` の `no-store` は外側が付ける」に直した。A の HO-51 内訳(当時の記述)には、2026-11-23 の訂正を追記した |
| [Suggestion 2] 4.1 の「機能パッケージを知っているのは `main.py` だけ」が、`config.py` が `admin/settings.py` の設定型を import する設計と矛盾 | **妥当**(D 4.1 の同じ節と 6章の許可表が `config` → `admin`(設定型)を許可している) | D 4.1 を「機能パッケージを生成・組み立てるのは `main.py` だけ(…`config.py` は admin 実装時に、設定型を持つモジュールの入口だけを参照する。R12)」に直した。A 7章・R1 の「組み立ては `main` だけ」は正確なので変更なし |

## 補足

- `apps/api/README.md` の古い注記は、レビューでも「別タスクにしても問題ない」とされており、スコープ(コード変更なし)を優先して未対応のまま。
- 実装側の docstring(`server/app.py`・`middleware.py`)に `no-store` の担当を誤って書いた箇所はない(確認済み。`middleware.py` は「例外の吸収のため」と書いている)。
- `apps/` に変更なし。

## 変更したファイル

- `docs/v0.x/system-design/api/admin/admin-api-module-structure-v0.1.md`
- `docs/v0.x/system-design/api/api-base-design-v0.1.md`

## 未対応事項

- 0007 のとおり(変更なし)

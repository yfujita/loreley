# 0002 P1 事前準備(比較基準・ベースライン)

作成: 2026-11-23(メインエージェント)

## 実施内容

- プラン(0001)のユーザー承認を得た(2026-11-23。前提 P-c・P-d・P-f を含め、変更の指示なし)。
- 比較基準: `c0b6e40010ce710de06c14495dadbec93edbf551`(`HEAD`。main)。
- 作業ディレクトリ: `git status` は本タスクの `agent_tasks/20261123_update_api_design_after_base_impl/` のみ未追跡。`git diff --stat c0b6e40 -- docs/v0.x/system-design/api/ apps/` は空(対象 4 文書・`apps/` とも未変更)。
- 実装の状態: `cd apps/api && uv run pytest -q` → **310 passed**。

## 旧構成 grep のベースライン(改訂前)

対象 `docs/v0.x/system-design/api/`。D = `admin/admin-api-module-structure-v0.1.md`、A = `api-base-design-v0.1.md`。

| パターン | D | A |
| --- | --- | --- |
| `server/health` | 695 | 365・367・369(HO-51 内訳。経緯の記録なので残す) |
| `create_app(settings` | 214・671 | 365・369(同上) |
| `admin_app` | 74(`adminEntry` 内)・118・175・205・214・215・670・671・677・689・706 | 369・376(HO-51 内訳) |
| `server --> adminEntry` | 96 | - |
| `load_config` | 201・665 | - |
| `ApiConfig` | 199・666 | - |
| `HO-1〜HO-50` | 7 | 8(改訂履歴)・253・383(HO-51 の説明。経緯の記録) |
| `AAM-U-2` | 217・814・855・868 | 360・370・373 |
| `BAPI-U-2` | 217・814・868 | 194・370・424・491 |
| 「本タスクでは作らない」 | 189 | 365(HO-51 内訳) |

(`HO-1〜HO-50` は B 9 行目・C 7 行目、改訂履歴 B 8 行目にもある。行番号は改訂前。)

## 変更したファイル

- なし(作業記録のみ)

## 未対応事項・次にやること

- P2: D の改訂を document-writer に依頼する。

# 0002 要件確認の回答(要確認 4 点)

- 日付: 2026-11-26
- 経緯: 0000 末尾の「要確認」4 点をユーザーに確認した。すべて推奨案が選ばれた。他に不明点・矛盾はないと判断し、`requirements-clarifier` は省略した(0000 が設計 E・F の参照つきで具体的、かつ 4 点がすべて確定したため)

## 確定した要件

1. 依存の範囲: 0000 の 11 パッケージのみ。lint/test のスクリプト枠も入れない
2. プレースホルダーの `src/`: Vue Router を最小で組み込む(`createWebHistory(import.meta.env.BASE_URL)`・1 route)
3. 検証用の Node: `docker run node:24`(ホストの Node は変えない)。README に `.nvmrc` の版への切り替えを書く
4. `.gitignore`: `apps/web/.gitignore`(既存の `apps/*` の流儀に合わせる)

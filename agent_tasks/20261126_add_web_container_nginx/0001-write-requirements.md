# 0001 要件定義(0000)の記載

- 日付: 2026-11-26
- 経緯: ユーザーの依頼(「20261126_create_admin_ui_system_design で追加したタスク二件の要件定義を記載して」)により、メインエージェントが `0000-requirements-definition.md` を記載した。通常は要件定義の記載はユーザーが行うが、今回はユーザーの明示的な依頼による
- 参照元: 元タスクの 0016、E v0.2 の 3.3〜3.6・12.8、F v0.2 の 8.9、A の HO-53〜58、元タスクの 0004(X-C1・X-C2)・0005・0007。実コード・設定(`deploy/compose/compose.yaml` の `api` の `ports`、`tests/integration/api/compose.test.yaml` の `/app/web` の mount、`web_dist`・`WEB_DIST` の参照ファイル、`apps/web` が存在しないこと)
- 記載で補った判断・「要確認」として 0000 の末尾に列挙した点(推奨案つき):
  1. 結合テストでの `web` の扱い(実 `web`・軽い代役・IT の対象外。推奨は代役)
  2. `web` の healthcheck と EP-13 の確認先(推奨は `/admin/` の 200。設計は `/healthz` を置かない)
  3. `WEB_HOST_PORT` の既定値(推奨 8090)
  4. 着手の順序(スキャフォールドの後)
- 範囲の線引き: `apps/web` のアプリ本体・設計書の追従改訂(HO-59・60・65)・`web` 経由の接続確認の IT 新設・HTTPS/認証はスコープ外
- 変更したファイル: `0000-requirements-definition.md`、`STATUS.md`
- 未対応事項・次にやること: 要件確認(`requirements-clarifier`)で 0000 末尾の「要確認」をユーザーに確認 → プラン作成。ユーザーのレビュー・修正を受けてから確定させる。**着手は `apps/web` の最初のスキャフォールドの後**

# 0001 要件定義(0000)の記載

- 日付: 2026-11-26
- 経緯: ユーザーの依頼(「20261126_create_admin_ui_system_design で追加したタスク二件の要件定義を記載して」)により、メインエージェントが `0000-requirements-definition.md` を記載した。通常は要件定義の記載はユーザーが行うが、今回はユーザーの明示的な依頼による
- 参照元: 元タスクの 0016(前提タスクの枠の起票)、E v0.2 の 5.2・12.7・12.8、A の HO-52、元タスクの 0004(S-D1・X-ED2・J-O2・J-O4)、実コード(`apps/api/src/loreley_api/admin/schemas/sources.py`・`openapi_export.py`)
- 実コードで確認した現状: `UpdateSourceBody` の `ttl_days`・`ttl_seconds` は `int | None = None` と明示的 null を拒否する `field_validator`。`openapi_export.py` の docstring は「リポジトリにコミットしない」
- 記載で補った判断(ユーザー確認が要るなら次の要件確認で聞く):
  - 「どちらか一方が必須」の OpenAPI での表現(`oneOf` など)は行わない(HO-52 は「任意かつ非 null」までを求めており、型生成の複雑化を避ける)
  - jobs の `sort` の列挙化・`warnings[].code` の型は HO-52 の「任意」を踏まえ、任意項目としてプランで判断する
  - 実行時の挙動は変えない(制約として明記)
- 変更したファイル: `0000-requirements-definition.md`、`STATUS.md`
- 未対応事項・次にやること: 要件確認(`requirements-clarifier`)→ プラン作成。この要件定義は、ユーザーのレビュー・修正を受けてから確定させる

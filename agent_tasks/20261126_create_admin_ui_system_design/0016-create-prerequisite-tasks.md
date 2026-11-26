# 0016 前提タスクの枠の起票

- 日付: 2026-11-26
- 経緯: 完了報告での確認(0014 のユーザー判断待ち)に対し、ユーザーが「2 本とも枠だけ起票(推奨)」を選択した
- 作成(`scripts/new-task.sh`。雛形のみ。要件 0000 の記載はユーザーが行う):
  - `agent_tasks/20261126_fix_admin_openapi_types/`(前提タスク A: `ttl_days`・`ttl_seconds` の OpenAPI 型、`openapi_export.py` の docstring。参照: A の HO-52、E 12.8)
  - `agent_tasks/20261126_add_web_container_nginx/`(前提タスク B+C: `web` コンテナ(Nginx)・compose(`api` の `ports` を外す)・`api` の EP-13 の `web` 判定を `HttpHealthCheck` に置換・`web_dist.py`/`LORELEY_API_WEB_DIST_DIR` の撤去・IT の追従・dev プロキシ・README。参照: A の HO-53〜57・HO-55・HO-56、E 12.8、F 8.9。`apps/web` の最初のスキャフォールドの後に着手し、`web` 経由の接続確認と初回リリースの前に完了)
- 両タスクの要件 0000 を書くときの参照元: 本タスクの E v0.2 の 3.3〜3.6・5.2・12.7・12.8、F v0.2 の 8.9、A の HO-52〜68、0004・0005・0007

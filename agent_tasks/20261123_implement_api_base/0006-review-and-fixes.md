# 0006 レビュー(1回目)と指摘への対応

日付: 2026-11-23
比較基準: `6fb61a0`(`apps/api/` は新規、`docs/` は api-base-design-v0.1.md のみ変更)

## レビュー結果(1回目)

| レビュー | 結果 |
| --- | --- |
| code-reviewer | Critical・Important なし。Suggestion 5、Nitpick 4。AAM-U-2 の方式は MVP 構成で妥当(実 uvicorn・入れ子マウント・HEAD・lifespan などを実行して確認) |
| test-reviewer | Critical なし。Important 3、Suggestion 6、Nitpick 4。300 件通過。変異検証で主要分岐は検出されたが、`main()` の配線と設定エラーの10件打ち切りが未検証 |
| document-reviewer | Critical なし。Important 4、Suggestion 5(他文書の範囲表記を含む)、Nitpick 2 |

## 対応した指摘

### 実装・テスト(code-implementer。307 passed へ。変異で確認)
- test-reviewer Important 1・3: `main()` の配線テスト(`uvicorn.run` を差し替え、host/port/`log_config is None`/`access_log is False`/ワーカー・reload なしを確認、root のレベル)と、`build_app()` の `/healthz` DEBUG・`/nope` INFO のテストを追加。変異(`access_log=True`、`debug_access_log_paths=()`、`configure_logging` の削除、`workers=2`)はすべて検出された
- test-reviewer Important 2: `describe_settings_errors` の「先頭10件+`... and 1 more`」とセンチネル非出力のテストを追加
- test-reviewer Suggestion/Nitpick: 子プロセスのアサーションを `invalid settings: port: int_parsing` に強化、`TestClient(build_app())`(lifespan 実行)まで接続禁止下で確認、ログ検査の統合(`log_method_calls_in`)、`import loreley_api.server.app` 形の自己テスト追加、構成固定の `==` を `in` に緩和、`openapi_url` を明示必須に、重複アサーション削除、ApiError・HTTPException(418) の `no-store` 追加、Starlette の scope 共有依存の docstring
- code-reviewer Suggestion: アクセスログのテンプレートが Starlette の `Mount`(`methods` を持たない route)で接頭辞が二重になる問題を修正(`-` にする)。回帰テスト追加。`health/__init__.py` の docstring、`create_app`・`SubAppMount` の副作用の docstring

### 設計書・README(メインエージェント)
- document-reviewer Important: HO-51 を要約+表直後の「HO-51 の内訳」に分け、D の章別改訂、A 7章の改訂内容(A 2.1 は変更なし)、AAM-U-2 の確定(D 4.2・8.3・8.4 と A 10.4 BAPI-U-2・HO-48 の更新を明記、**AAM-P-23 は承認済みの案のため D 改訂時にユーザー確認を取る**)、OpenAPI を公開する場合はサブアプリ側で設定、を追記。README に「実装は D と一部異なる。D の追従改訂までは実装を正とする(HO-51 参照)」と `details` を追記
- document-reviewer Suggestion: `ApiError` の署名・`error_response` の `headers`・`display_text` 不作成・ログ検査の対象メソッド・`server` 専用設定 dataclass なし・README の実在、基盤が未実装のもの(本文上限・厳密 JSON・`exclusive`・`BlockingRunner` など)、確認した版(FastAPI 0.165.0・Starlette 1.10.0)、`ClientDisconnect`、設計タスクの後に実装タスクが追加した旨、改訂履歴への1文追記
- code-reviewer Suggestion: サブアプリを素の `FastAPI(...)` で作ると `/openapi.json` が既定で公開される注意、`FastAPI(root_path=...)` で壊れうる注意を HO-51 に記載

## 対応しなかった指摘と理由

- code-reviewer: `ClientDisconnect` の別扱い(基盤の範囲では顕在化しない。HO-51 に申し送り)、`HEAD /healthz`(A 6 は GET と定める)、`log_access` フラグの分割(2値だけで許容)、pyproject の fastapi 下限の引き上げ(Docker・CI は `--locked`。変更しない。確認した版を HO-51 に記録)
- test-reviewer: 許可表を見るテストの parametrize 化(振る舞いは別の自己テストで確認済み)、`test_errors.py` のディレクトリ名依存(実害が小さい)
- document-reviewer: B・D・admin-api-architecture の「HO-1〜HO-50」表記(本タスクの方針「設計書本文は変更しない」により、別タスクで揃える)。出典に 0005 を足す件は、0005 を含めて HO-51 に記載済み

## 検証(メインエージェントが再実行)

`cd apps/api`: `uv run pytest` 307 passed、`uv run ruff check` 通過、`uv run ruff format --check` 36 files formatted、`uv lock --check` 通過。`git status` で `apps/api/`・`agent_tasks/`・設計書 api-base-design-v0.1.md 以外に変更なし。

## 次にやること

- 再レビュー(test-reviewer: Important の解消確認、document-reviewer: Important の解消確認)。code-reviewer は Critical・Important がなく、Suggestion の修正は局所的なため再レビューを省略する
- task-reviewer(タスク全体)

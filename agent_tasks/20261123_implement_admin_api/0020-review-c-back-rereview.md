# 0020 レビュー R-C 後半の再レビューの結果

日付: 2026-11-24

## 結果

比較基準 `b9f09e4..32d595b`(指摘対応コミット)。同じレビュアー(`code-reviewer`・`test-reviewer`)で再レビューした。

### code-reviewer: 指摘なし(Critical 0 / Important 0 / Suggestion 0 / Nitpick 0)
- README 5 章冒頭の修正は、`env -i` で `load_settings()` を動かして確認(実ネットワークなし): `DASHBOARDS_URL`・`CRON_TIMEZONE`・`LLM_HEALTH_URL`・`EMBEDDING_HEALTH_URL`・`DASHBOARDS_HEALTH_URL` を空文字にすると `None`(README の列挙と一致)。`OPENSEARCH_USERNAME` だけ/`OPENSEARCH_PASSWORD` だけを空にすると `opensearch_credentials_incomplete` で起動失敗(「片方だけが空文字だと起動に失敗する」と一致)。`OPENSEARCH_CA_CERTS_PATH` を空にすると `''` のまま設定として扱われる。フラグメント付き URL は `url_fragment` で失敗(C 7.3 と整合)
- `_install_openapi_adjustment` は正しい: 2 回目は同じ dict を返し再調整しない/初回後にルートを追加すると FastAPI が再生成し、新しい dict は再調整されて 422 は復活せず追加ルートも反映/スキーマ名の衝突では 1 回目も 2 回目も `ValueError` が伝わり、未調整のスキーマを黙って返さない/調整は冪等/`openapi()` は同期関数でイベントループ上は原子的/メモリの増加なし
- `_invalid_body` への改名は 3 か所で共有され、`_too_large` への参照は残っていない。`_Unconnected.__getattr__` のダンダー対応・`pyproject.toml` のコメント(`tomllib` で読める・`uv lock --check` が通る・`uv.lock` に差分なし)も問題なし
- 補足(対応不要): `OPENSEARCH_USERNAME` と `OPENSEARCH_PASSWORD` の両方を空文字にすると、検証を通って空の認証情報が設定される(既存の挙動。README の「片方だけ」の表現とは矛盾しない)

### test-reviewer: 指摘なし(Critical 0 / Important 0 / Suggestion 0 / Nitpick 2)
- `ClientDisconnect` のテスト 2 本は意味のあるアサーションを持つ。変異 10 件(`exc_info=True`・`request.url.path` を `%s`/f-string/`extra` でログに足す・`except Exception` へ広げる・`except (ClientDisconnect, ValueError, RuntimeError)`・`except (ClientDisconnect, OSError)` へ広げる・捕捉の無効化・メッセージ変更・WARNING を 2 件に増やす)をすべて検出
- Suggestion 対応: `ExpectedOperation` の `ok_statuses`・`error_codes` は B から手書き(実装から導出していない)で、全 EP が B のエラー表と一致。EP-03・04 の 400 から `config_invalid` を落とす/EP-02 の 404 を替える/EP-05 の `status_code` を 200 に替える/EP-01 の 503 に余計な code を足す変異を検出。冪等化テスト 4 件は旧実装に戻すと 3 件が失敗(残り 1 件はキャッシュ中は再調整しない性質を固定)。`_Unconnected` のダンダー対応のテストも検出力あり。`run('opensearch', …)` の変異は検出
- pytest 3410 passed、逆順実行でも 3410 passed(99〜100 秒)。グローバル状態の汚染・フレークなし。プロセスの残りなし
- Nitpick: (1)`test_blocking_isolation.py` は `run('probe', …)` の取り違えを検出しない(読み取りが probe 区分を使わないため。relay 単体が検出するので据え置き)(2)`packaging` が `pyproject` に明示されていない(`pytest` の必須依存として `uv.lock` に入っており実害なし。据え置き)

## 判断(Nitpick)

- (1)据え置き: relay の単体テストが区分を検出している。結合テストに probe を使う EP-13 の読み取りを足すにはプローブ先の用意が要り、割に合わない
- (2)据え置き: `pytest` が `packaging` を必須依存にしている。必要なら dev 依存に足す(後続)

## 結論

R-C(前半・後半)の Critical・Important はすべて解消。プランのレビューフェーズを完了。次は `task-reviewer`(タスクレビューフェーズ)。

## 次にやること

- `task-reviewer` によるタスク全体のレビュー(要件定義 0000・確認 0001・プラン 0002・作業記録 0003〜0020・実際の変更の突き合わせ)
- 指摘対応後、完了チェックリストの確認 → PR 作成(ユーザー確認のうえ)

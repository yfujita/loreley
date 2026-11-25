# 0008 P4: 障害系の IT(AIT-90・91・92)

日付: 2026-11-25
担当: code-implementer(実装)、メインエージェント(静的検査・残骸の再確認)

## 実施内容

- `tests/integration/api/test_90_component_failures.py`(AIT-90・91・92)を新規追加
- `support.py` 追加のみ: `ComposeControl.stopped(service)`(停止区間の context manager。stop は `try` の内側、`finally` で `start` と healthy 待ち)、`ComposeControl.wait_all_healthy`、`SERVICES_TO_AWAIT_AFTER_START`、`require_controllable_service`(許可リスト検査の共通化)、`fetch_component_states`、`wait_for_components_normal`、`COMPONENT_RECOVERY_*`
- `conftest.py` は変更なし。conftest の autouse(アイドル待ち)は停止区間の外(開始前・復旧後)でだけ動くため、OpenSearch 停止中に EP-09 が読めなくても影響しない(ファイル冒頭 docstring に記載)
- 安全策: 許可リスト `{crawler, indexer, opensearch}`・プロジェクト `loreley-it` 固定・`LORELEY_IT_ALLOW_COMPOSE_CONTROL=1` でなければ 3 件とも skip・復旧待ち上限 300 秒。OpenSearch 停止後は opensearch・indexer・crawler・api の 4 つを待つ

## 変更したファイル

`tests/integration/api/test_90_component_failures.py`(新規)、`tests/integration/api/support.py`(+69/-3)。`apps/`・設計書は変更なし。

## 判断・設計上の理由

- 設計が複数の値を許す箇所(EP-13 の `reason`、EP-06 の 503 の code)は両方を受け入れ、実機の値を `[observed]` 付きで print する(`-rP` で結果ログに残る)
- AIT-91 の停止中クロールは、観測結果が設計 10.2 と一致したため `failed`・`rerunnable=true`・`latest_for_source=true` を断定するアサートにした
- AIT-91 のソース削除は、実行待ち中ではなく失敗後の状態で `deleting` 系(EP-01・02 の `status=deleting` と `delete_job`、EP-04・06 の 409 `source_deleting`、同内容 EP-03 の 409 `source_already_exists`(`details={"status":"deleting"}`)、EP-11 200)を確認(安定して確認できるため)。削除に失敗しても文書 2 件が残ることも確認
- 復旧後は EP-13 `normal` と EP-01 200 を最大 60 秒ポーリング。AIT-92 は直後に実クロールが `succeeded` になり文書が 2 件に増えるまで確認

## 検証結果

- P4 冒頭の実機確認(compose v2.3.3): `stop crawler`/`stop indexer`/`stop opensearch` は対象 1 つだけが止まり、他のコンテナは Up のまま・コンテナ ID も不変(再作成なし)。OpenSearch 停止中も crawler・indexer は healthy のまま(healthcheck が OpenSearch に依存しない)。`start opensearch` から 4 サービスが healthy になるまで約 56 秒。`start crawler`/`start indexer` は依存の使い捨て `opensearch-init` を同じコンテナで再実行する(冪等。害なし)
- ruff check・format(10 files)、`pytest --collect-only`(23 件)、TEMPORARY の残りなし: OK(メインエージェントも再実行)
- クリーンな状態から `scripts/run-api-integration-test.sh`(`--keep` なし)を 2 回連続で全件実行: いずれも 23 passed、終了コード 0(pytest 344.8 秒・342.8 秒、スクリプト全体 6 分 58 秒)。不安定なテストなし。障害系単体は AIT-90 約 35 秒・AIT-91 約 49 秒・AIT-92 約 85 秒
- 途中失敗時の後始末: AIT-92 の停止区間内に一時的な `assert False` を入れて実行 → 1 failed のあと `finally` で 4 サービスが `running healthy` に戻り EP-13 も全 normal(約 70 秒)。確認後に元へ戻し、退避コピーとの `diff` 一致を確認
- 許可リスト外(`stop api`・`stop opensearch-init`・`down crawler`・`stopped("api")`)は docker を呼ぶ前に `ValueError`
- 終了後: `loreley-it` のコンテナ・ボリューム・ネットワーク・`data/` なし、ポート空き、`docker ps -a` は P4 開始前の出力と一致(他プロジェクトの `opensearch-opensearch-1` のみ。メインエージェントも再確認)

## 発見事項(実機の観測値。設計との食い違いなし)

- EP-13 の `reason`: 停止した crawler・indexer・opensearch はすべて `abnormal` / `name_not_resolved`(api はコンテナ内から停止コンテナの名前を引けない。`connection_refused` は出なかった)
- AIT-90(Crawler 停止): EP-03〜08 は 503 `crawler_unreachable`(`retryable=true`)。副作用なし(新規ソースは 404 のまま、S は `active` で文書 1 件、ロックなし)。EP-01・02・09・10・11・12・14 は 200。復旧後 EP-06 が 202 → `succeeded`
- AIT-91(Indexer 停止): (a) クロールは受付 202 のあと `failed` / `failure_reason=indexer_unavailable` / `failure_detail="Indexer が応答しない(connection_error)"`、`rerunnable=true`・`rerun_blocked_reason=null`・`latest_for_source=true`、ロック解放。(b) ソース削除は `failed` / `indexer_unavailable` / `failure_detail="Indexer が応答しない(discard_deletions。connection_error)"`(順 1 の discard で失敗)。(c) 復旧後 EP-05・EP-06 の再実行とも `succeeded`。削除ソースは EP-02・11 が 404、EP-01 から消え、文書・設定も 0。古い失敗ジョブは `latest_for_source=false`・`rerunnable=false`・`rerun_blocked_reason=superseded`
- AIT-92(OpenSearch 停止): EP-01・02・09・10・11・12 は 503 `unavailable`(`retryable=true`)。EP-13 は `opensearch=abnormal`(`name_not_resolved`)、`api`・`web` が `normal`、`crawler`・`indexer` はどちらも `normal`/`reason=null`(`/healthz` が OpenSearch に依存しないため)。EP-14 と `/healthz` は 200。EP-06 は 503 `crawler_unavailable`(`retryable=true`。`crawler_unreachable` ではない)。復旧後 EP-01 200・EP-13 全 normal・クロール `succeeded`・文書 2 件
- Crawler の Indexer 不達時の失敗は速い(リトライ 3 回・バックオフ 1・2 秒)。クロール・削除とも数秒で `failed` になり、ポーリング上限 120 秒には達しない

## 未対応事項・次にやること

- P5 の結果文書に載せる: 上記の観測値、`start crawler`/`start indexer` が `opensearch-init` を再実行すること、全 23 件の所要時間(初回ビルドなしで pytest 約 343〜345 秒)
- 未実施: shellcheck(未インストール)、アプリの単体テスト・ruff(`apps/` 無変更のため P5 で退行確認として実施)、既存 Crawler・Indexer IT の再実行(P5)
- 次: P5(最終確認と記録)。README・結果文書の作成、`apps/api` の単体テスト・ruff、既存 IT 再実行、api IT の最終 2 回連続

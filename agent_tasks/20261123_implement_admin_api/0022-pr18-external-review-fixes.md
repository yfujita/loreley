# 0022 PR #18 の外部レビュー指摘への対応

日付: 2026-11-25

## 経緯

PR #18(1 本で作成)に対し、ユーザーが外部のレビュー結果(静的レビュー。GitHub 上の差分・主要実装・設計書・作業記録に基づく。テストの独立再実行・実機再現はなし)を貼り付け、「指摘を確認して、適切であれば対応して」と依頼した。判定は「軽微な修正後にマージ推奨」(Critical 0 / Important 1 / Minor 1)。メインエージェントが各指摘を実コード・実際に書き出した OpenAPI・設計書で事実確認してから対応した。

## 指摘の確認結果と対応

| 指摘 | 確認結果 | 対応 |
| --- | --- | --- |
| **I-1(Important)** EP-11 の必須クエリ `tab` が OpenAPI 上は任意。`items_per_page` の列挙(25・50・100)も反映されていない | **事実**。`env -i` で書き出した OpenAPI で `tab` は `required: false`・`anyOf[string, null]`、`items_per_page` は整数全般(EP-09・EP-11)。B 6.1 は `tab` を必須(`skipped`・`extract_failed`・`oversize`・`summary_pending`。欠落は `required`、それ以外は `unsupported`)、B 2.1 は `items_per_page` を 25・50・100 と定義 | 修正した(下記) |
| **M-1(Minor)** 登録・更新のリクエスト本文と Crawler 応答本文の上限がともに 1 MiB で整合しない | **事実**。`common/http/body.py` の `MAX_REQUEST_BODY_BYTES`=1 MiB、`infrastructure/crawler_client/parsing.py` の `RESPONSE_MAX_BYTES`=1 MiB。Crawler の `_source_body`(`api/responses.py`)は受け取った設定に `status`・`updated_at`・`ttl` などを足して返すので、1 MiB いっぱいの設定は保存できても応答が上限を超え、保存は成功しているのに 502 `crawler_error` になり得る | レビューは「後続タスクでも可」としたが、「保存は成功したのにエラーが返る」状態を避ける小さな修正なので今回あわせて対応した。**設計書 C 4.1(「本文は 1 MiB まで」)と食い違う変更**なので申し送りに残す |
| 「実装規模」の所見(249 ファイル・約 33,000 行。一度しか使わない抽象化・ファイル分割・アーキテクチャテストの規則・テスト件数より振る舞いの重要性を意識) | 助言 | 対応しない(現状の大規模なリファクタリングは不要との所見。今後の開発の指針として受け取る) |
| 既知のリスク・後続タスクの表(認証・CSRF、実機検証、期限超過後のスレッド、OpenAPI の TTL 排他・null 許容、設計書の差分ほか) | すべて 0021・PR 説明・README に記載済み(新規の指摘ではない) | 対応なし。**OpenAPI の `ttl_days`・`ttl_seconds`(`integer \| null`)の不整合は「フロントエンド実装前」の対応推奨**とのこと。0017・0021 の C に既に記載。フロントエンドの型生成を始める前に対応する |
| 「ダッシュボードの期限超過後に残留するスレッド」は負荷試験 | AAA-U-10(0018・0021 の B) | 対応なし(既存の申し送り) |

## 修正内容(code-implementer。メインエージェントが検証を再実行)

### I-1
- 実行時の検証(違反をまとめて返す・検証順序・エラー形式)は変えない。レビューの提案どおり、`read_document_query` の引数を `tab: DocumentTab` に置き換えると既存のエラー集約や検証順序に影響するため行わず、**`admin/app.py` の `_adjust_openapi()` で必須性と列挙を反映した**(src のルーターは未変更)
- 宣言の表 `_QUERY_PARAMETER_RULES`(`_QueryParameterRule`: operationId・パラメータ名・選択肢・required)と、適用処理 `_apply_query_parameter_rule` を追加。表の対象が見つからないときは `ValueError`(操作名・パラメータ名の変更で黙って外れるのを防ぐ)
- 反映した内容と値の導出元(定数から導出し、手書きで複製していない):
  - EP-11 `tab`: `required: true`、string の列挙(`DocumentTab`)。`anyOf[string, null]` は外して `type`+`enum` に
  - EP-09・EP-11 `items_per_page`: integer の列挙 `[25, 50, 100]`(`ITEMS_PER_PAGE_CHOICES`)。`default: 25` は維持
  - EP-09 `status`: 任意のまま、string の列挙(`ACTIVE_FILTER`=`active` と `JobStatus`)。B 5.1 が `queued`・`running`・`succeeded`・`partially_succeeded`・`failed`・`cancelled` または複合の `active` と限定し、それ以外は `unsupported` としているため
  - `sort`(タブごとに許容項目が違う)・`page`・`source_id`・他の EP は変えていない
- 書き出した OpenAPI(`env -i` で確認):
  - `/sources/{source_id}/documents` の `tab`: `required: true`・`enum: [skipped, extract_failed, oversize, summary_pending]`・`type: string`
  - `/jobs` の `status`: `enum: [active, queued, running, succeeded, partially_succeeded, failed, cancelled]`
  - `/jobs`・`/sources/{source_id}/documents` の `items_per_page`: `default: 25`・`enum: [25, 50, 100]`
- テスト 6 件(`tests/admin/test_openapi.py`): `tab` の必須と列挙が `DocumentTab` の全値と一致、`items_per_page` の列挙(EP-09・EP-11)、EP-09 `status` の列挙、他のパラメータが変わらないこと、など。公開と書き出しが同一であること(既存)・実行時の挙動(既存のルーターテスト: `tab` なしは 400 `required`、不正な `tab` は 400 `unsupported`、`items_per_page=10` は 400 など)は引き続き通る

### M-1
- `admin/base/constants.py` の `CRAWLER_RESPONSE_MAX_BYTES` と `infrastructure/crawler_client/parsing.py` の `RESPONSE_MAX_BYTES` を、どちらも **2 MiB**(`2 * 1024 * 1024`)にした。理由コメントも更新。`MAX_REQUEST_BODY_BYTES`(1 MiB)は変えていない。応答は設定+固定の数項目なので、リクエスト上限+余裕で足りる
- テスト: `tests/admin/base/test_constants.py` に 2 件(2 つの上限の一致、応答上限がリクエスト上限 + 16 KiB 以上)、`tests/admin/routers/test_write_eps_over_http.py` に 4 件(1 MiB + 4 KiB の正常な応答で EP-03(201)・EP-04(200)が成功、2 MiB 超の応答は登録・更新とも 502 `crawler_error`)、`tests/infrastructure/crawler_client/test_parsing.py`・`test_http_client.py` の既存テストを新しい上限に追従(`RESPONSE_MAX_BYTES` 参照のままテスト名だけ改名)

## 検出力確認(実装担当。すべて元へ戻し `diff` で確認)

- I-1: `tab` の `required=True` を `False` に/`tab` の宣言を削除/`tab` の列挙の値を 1 つ落とす/`items_per_page` の選択肢を 2 つに減らす/`status` から `active` を落とす → いずれも対応するテストが失敗
- M-1: 上限を 1 MiB に戻す → 4 件が失敗(EP-03・EP-04 の 1 MiB + 4 KiB 応答の成功、余裕を見る定数テスト、`test_parsing.py` の一致テスト)

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 3423 passed(PR 提出時 3410)/ `uv run ruff check`: All checks passed / `uv run ruff format --check`: 249 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし。プロセスの残りなし。変更は src 3 ファイル(`admin/app.py` +62・`admin/base/constants.py`・`infrastructure/crawler_client/parsing.py`)とテスト 5 ファイル(計 8 ファイル・約 250 行)。`read_document_query` などルーターは未変更(実行時の検証の挙動は不変)
- `env -i` で書き出した OpenAPI の該当パラメータを自分でも確認(上記)

## 設計書との食い違い・申し送り(設計書は未変更)

- **C 4.1・C 9章の上限の表**: 「Crawler の応答本文は 1 MiB まで読む」と実装(2 MiB)が食い違う。登録・更新の応答は設定に `status` などを足して返すため、リクエスト本文の上限いっぱいの設定が保存できても 502 になる(保存は成功しているのにエラー)ことを避けるために広げた。C 4.1 と C 9章の上限の表、`crawler-api` 側の記述が言及していれば 2 MiB に追従改訂する(0021 の A に追加)
- **B 6.1・B 5.1・B 2.1**: OpenAPI の `tab`(必須・列挙)・`status`(列挙)・`items_per_page`(列挙)を実装が OpenAPI に反映した。設計書の記述どおりで、食い違いはない

## 修正差分のレビュー(code-reviewer)

比較基準 HEAD `922acdc` の作業ツリーの差分。**指摘なし**(Critical 0 / Important 0 / Suggestion 2)。
- 確認済み: ルール適用前後の OpenAPI の差は 4 パラメータ(EP-11 の `tab`・`items_per_page`、EP-09 の `status`・`items_per_page`)のみで、他のパラメータ・他の EP への副作用なし/`_adjust_openapi` の冪等性(2 回適用しても一致)/`operationId`+`in: query`+`name` で特定し見つからなければ `ValueError`/実行時の検証は不変(ルーター未変更。`tab` 欠落は 400 `required` のまま)/M-1 の 2 つの定数の一致と、リクエスト上限 + 16 KiB 以上の余裕/メモリ・DoS(上限を超えた時点で読むのをやめる。`crawler` 区分の同時実行上限 4 を掛けても十数 MiB)
- 検証(対象テスト 899 passed)
- Suggestion 1(取り込み): 2 MiB の余裕は「Crawler が項目を足す分」しか見ていない。Admin が Crawler へ送る本文は `ensure_ascii`(既定 True)で再エンコードされるため、非 ASCII だけの 1 MiB 級の設定は `\uXXXX` 表記で膨らみ、応答が 2 MiB を超えうる(仮定。Crawler 側の応答エンコードと Crawler 自身のリクエスト上限は未確認。1 MiB 級の設定自体が非現実的)。`constants.py` のコメントを「いっぱいの設定が」から「に近い設定が」「通常の設定では避ける」に弱め、窓が完全にゼロにならないことを明記した。設計書の追従改訂の申し送りにも「非 ASCII では余裕が足りない可能性」を添える
- Suggestion 2(据え置き): 宣言の表 `_QUERY_PARAMETER_RULES` が対象のパラメータ(ルーター)から離れた場所にある。名前を変えれば `ValueError` で気づけるので実害は小さい。将来増えるなら `Query(json_schema_extra=…)` に寄せる手もあるが、`anyOf`・`required` の扱いが FastAPI の生成物に依存するため好みの範囲

## 未対応事項・次にやること

- コミットし、PR #18 のブランチに push する(PR の更新。ユーザーの依頼「指摘を確認して、適切であれば対応して」に基づく)
- OpenAPI の `ttl_days`・`ttl_seconds`(`integer | null`)の不整合: フロントエンドの型生成を始める前に対応する(0017・0021 の C)

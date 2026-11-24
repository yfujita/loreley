# 0015 レビュー R-C 前半(P5a・P5b・P6)と指摘対応

日付: 2026-11-24

## レビュー結果

比較基準 `5dc68c4..467da20`。データ削除・ロック解放・クロール起動を Crawler へ中継する高リスクの区間のため、`code-reviewer`・`test-reviewer` を並列実施した。

### code-reviewer: 指摘なし(Critical 0 / Important 0 / Suggestion 2 / Nitpick 4)
- 写像表 35 行と B 9.2 の一致、6 経路・メソッド・パスのエンコード、データ削除に関わる取り違え(`force_delete`・`rewrite_mode`、EP-05・07・08 が自分の操作だけを呼ぶ、strict で本文の誤 true を拒否)、再送なし・リダイレクト非追従・タイムアウト、409 の付随情報、入力検証(順序・単位変換・Admin が複製してはいけない検証を複製していない)、`SourceSettings` の分離、EP-13、R8、秘密値の漏えいはいずれも指摘なし
- 所見: 0013 の申し送り 6(`lock_state` を Crawler の応答後に読む)は、実装ではなく **D 5.0 が C・B とずれているので D 側を直すのが妥当**
- Suggestion: (S1)EP-07 の 400 で `details.errors[].field` が文字列でないと `TypeError` → 500(`translate._error_fields`)/(S2)Crawler 呼び出しの失敗理由が INFO 以上のログに残らない
- Nitpick: `_validate_settings` の不変条件が型で保証されない/`RegisterSourceBody` の継承の向き/操作の列挙値と呼び出しメソッドの対応が手書き/`routes.ROUTE_TEMPLATES` がテストからしか使われない

### test-reviewer: Important 1(Critical 0 / Suggestion 3 / Nitpick 4)
- 約 70 件のミューテーションのうち、実質的に生き残ったのは「EP-05・06・07・08 に許可外の HTTP メソッド(GET など)を足す」変異のみ(5 件)。`force_delete`/`rewrite_mode` の入れ替え 6 か所、EP-05 と EP-06 の経路入れ替え、EP-08 が削除ジョブを呼ぶ、`StartCrawlBody` の既定値を true、strict の無効化、`%2E` 置換の除去、`retries=True`、写像表 9 行の書き換え、`lock_state` の各変異、期限マージン、プローブの GET→POST などはすべて検出
- pytest 3252 passed。逆順・シャッフル・時間依存テスト 5 ファイルの 5 回連続・CPU 過負荷下でも成功
- **I1**: EP-05・06・07・08 に許可外メソッドが 405 になるテストがない(GET でクロール起動・削除ジョブ起動・ロック解放ができる退行を見逃す)
- Suggestion: S1(`lock_state` を応答後の時刻で読む仕様が時計を進めないテスト構造のため固定されていない)/ S2(`.invalid` の名前解決を引くテストの DNS 依存)/ S3(時間の上限の余裕が約 1 秒)
- Nitpick: N1(R8 (d) の限界の記載が (e) にも当てはまる)/ N2(テスト名と中身のずれ 2 件)/ N3(`test_translate.py` の `if not in_table:`)/ N4(フィクスチャ `crawler` の上書き)

## 指摘対応(code-implementer。メインエージェントが検証を再実行)

- **I1**: `test_crawl_operations.py` に 4 パス(delete-jobs=post、crawl-jobs=post、cancel=post、lock=delete)× 許可外メソッド(get/post/put/patch/delete)の 16 ケースを追加(405・`method_not_allowed`・`crawler.requests == []`)。EP-05・06・07・08 のルートに `@router.get` を足すと失敗することを確認(復元済み)
- **code S1**: `_error_fields` は文字列の `field` だけ集める。`field` が list・dict のケースを追加(502 `crawler_error`)。HEAD に戻すと `TypeError: unhashable type` で失敗することを確認
- **code S2**: `CrawlerRelay.send` が、`crawler_error`・`crawler_unavailable`・`crawler_unreachable`・`crawler_response_lost` のときだけ WARNING を 1 行(`operation`・`error_code`・`crawler_status`・`crawler_code`・`reason`)。`crawler_code` は写像表にある組み合わせのときだけ出し、表にない値は `unexpected`。ID・message・本文・`details`・`connector_config` は出さない。想定内の 4xx・成功は WARNING にしない。テスト 10 件(固定語彙の全文一致 6、想定内 4xx 3、成功 1)。すべてセンチネルが出ないことを `assert_secret_absent` で確認。ログ出力を外すと 6 件、表にない code をそのまま出すと 1 件が失敗(メインエージェントも差分を確認し、固定語彙と整数のみであることを確かめた)
- **test S1**: `crawler.behavior.before("start_crawl", lambda: clock.advance(seconds=40))` で応答後の時刻にし、取得 30 秒前の孤児ロックが `orphan`(呼び出し前の時刻なら `just_acquired`)になることを固定。`crawler_relay` の時刻取得を呼び出し前に変えると失敗
- **test S2**: `tests/conftest.py` に `unresolvable_invalid_hosts` フィクスチャ(`.invalid` の `getaddrinfo` だけを `gaierror` に。他の名前は実物へ委譲し 127.0.0.1 のスタブは妨げない)を追加し 4 件に適用。実 DNS のまま残すのは `test_http_client.py::test_an_unresolvable_host_is_before_send` の 1 件のみ(コメントに「DNS が応答しない環境で遅くなりうる」と明記)
- **test S3**: `tests/timing.py` に `TIMING_SLACK_SECONDS = 2.0` を集約し 3 ファイルが使う。期限マージンを 0/5 秒に変えるミューテーションは `test_dashboard.py` の 8 件が引き続き検出
- **N1〜N4・code Nitpick 1**: (e) にも同じ限界があると明記/テスト名を実態に合わせて改名(`test_without_a_slow_probe_the_response_does_not_wait_for_the_deadline`、`test_with_a_fixed_clock_the_top_level_and_every_component_checked_at_are_the_same`)/`NOT_IN_TABLE` の parametrize 化/フィクスチャ `crawler_stub` に改名/`_validate_settings` に `assert ... is not None`(型の絞り込みを兼ねる)

## 検証(メインエージェントが再実行、`apps/api`)

- `uv run pytest`: 3246 passed(以前 3252。減ったのは N3 の parametrize で表にある組み合わせの空打ちを無くしたため)
- `uv run ruff check`: All checks passed / `uv run ruff format --check`: 241 files already formatted / `uv lock --check`: OK
- `apps/api` 以外に差分なし。`src` の変更は `translate.py`・`crawler_relay.py`・`source_commands.py` の 3 ファイル(65 行)。一時的に足した GET ルートの残りなし

## 対応しなかった項目と理由

- code Nitpick 2(`RegisterSourceBody` の継承の向き)・3(操作の列挙値と呼び出しメソッドの手書き対応)・4(`ROUTE_TEMPLATES` がテストからしか使われない。R8 の 6 経路検査の目印として維持): 好みの範囲で、取り違えテストが 21 件の検出力確認つきで固定している。P7 以降に余裕があれば
- `test_secret_output.py` の DNS 依存: 据え置き(0007)

## 設計書追従改訂の申し送りの追加

- **D 5.0**: `lock_state` を読む時刻は、リクエスト先頭ではなく Crawler の応答後(C・B と合わせる。code-reviewer の所見で D 側を直すのが妥当)
- **C 8.5**: Crawler 呼び出しの失敗(`crawler_error`・`crawler_unavailable`・`crawler_unreachable`・`crawler_response_lost`)の WARNING(`operation`・`error_code`・`crawler_status`・`crawler_code`・`reason`。固定語彙と整数のみ。表にない Crawler の `code` は `unexpected`)を追記
- **C 11章**: 実 DNS を引くのは名前解決の分類の 1 件だけ(他は `getaddrinfo` を差し替える)と記載

## 未対応事項・次にやること

- `test-reviewer` による再レビュー(Important I1 の解消確認)。`code-reviewer` は Important なしで、`src` の変更も 65 行(メインエージェントが差分確認済み)のため再レビュー不要
- 解消後、P7(OpenAPI の `requestBody` 宣言・422 の除去・`operationId`・タグ・`OPENAPI_ENABLED` の公開配線・`openapi_export.py`・README・`server/` の結合確認・手動スモーク)

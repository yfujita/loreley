# 0016 レビュー R-C 前半の再レビューの結果

日付: 2026-11-24

## 経緯

0015 の指摘対応後、元の `test-reviewer`(a0026e0)に再レビューを 2 回依頼したが、同 agent がバックグラウンド作業を抱えたまま報告が受理されず(「報告は 1 回まで」の制約)、結果が届かなかった。ユーザーが「完了しているように見える」と指摘して再依頼したが、同じ状態だった。そのため同 agent での再レビューは打ち切り、**新しい `test-reviewer`(ade861c)に範囲を絞って再レビューを依頼した**(プランの「同じレビュアーで再レビュー」からの変更。完了を確認できる別 agent に切り替えた。再レビューの観点は前任の指摘 I1 と同じで、判定基準は変えていない)。

## 結果(新しい test-reviewer): 指摘なし(Critical 0 / Important 0 / Suggestion 1 / Nitpick 2)

- **I1 は解消**: `test_crawl_operations.py:632-660` の 405 テスト(4 パス × 許可外メソッド 16 ケース)は、405・`method_not_allowed`・`crawler.requests == []` の 3 点を assert する。scratch の複製で EP-05・06・07・08 のルートに許可外メソッド(get/put/patch/delete 等)のハンドラを足す変異 16 件は、すべて対応する 405 テストが失敗して検出された(未検出なし)
- `unresolvable_invalid_hosts`(`tests/conftest.py:36-49`): `.invalid` で終わる `str` のホストだけ `gaierror`、それ以外は実物へ委譲。127.0.0.1 のスタブを妨げない。`monkeypatch` で自動復元され他のテストに漏れない。逆順実行で全 3246 passed(59.91 秒)
- 任意項目はいずれも検出: 新しい WARNING ログのテスト(表にない code の出力、全 code のログ出力、`error.code` の置換、呼び出し削除、`warning`→`info`、`crawler_unavailable` の除外)/ 期限マージン(0 / 1.9 / 2.9 / 5.0 秒の 4 変異。`TIMING_SLACK_SECONDS = 2.0` に広げても検出力は落ちない。`DEADLINE_MARGIN_SECONDS == 1.0` の固定アサーションが `test_dashboard.py:242` にある)/ `translate._error_fields` の `isinstance(field, str)` を外す変異 / `NOT_IN_TABLE` の parametrize 化(ids つきで良い修正)
- リポジトリ本体は未変更(scratchpad の複製で実施)。起動したプロセスの残りなし(メインエージェントも確認)

## 判断(Suggestion・Nitpick)

- Nitpick: `conftest.py:45` の `host.endswith(".invalid")` は末尾ドット付き(`x.invalid.`)や素の `invalid` を拾わない。現状のテストは `*.invalid` のみで実害なし。据え置き
- Suggestion: `test_http_client.py:369` の 1 件は設計上、実 DNS に `crawler.invalid` を問い合わせる(DNS が応答しない環境で遅くなり得る)。意図的で冒頭に明記済み。据え置き
- Nitpick: 405 テストは EP-05 で `source_commands` 側の未呼び出しまでは見ない。Crawler 側の確認で足りるため追加不要

## 結論

R-C 前半(P5a・P5b・P6)の Critical・Important はすべて解消。P7 に進む。

## 次にやること

- P7: OpenAPI の `requestBody` 宣言・422 の除去・400 共通エラースキーマの宣言・`operationId`・タグ 6 種・`OPENAPI_ENABLED` の公開配線・`openapi_export.py`・`server/` の結合確認(Crawler 遅延でも他が応答)、README の更新、`tzdata` の直接依存化の判断、Docker の確認、手動スモーク

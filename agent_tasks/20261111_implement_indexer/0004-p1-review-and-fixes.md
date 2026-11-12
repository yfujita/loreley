# 0004 P1 レビューと指摘対応

日付: 2026-11-11 / 対象: 0003(P1)/ レビュー: code-reviewer、test-reviewer / 修正: code-implementer
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## レビュー結果

### code-reviewer(Critical/Important なし。可)
- Suggestion: 401/403 とスクリプトエラーが「文書固有の拒否」になる
- Suggestion: `delete_by_query` が 30 秒のクライアントタイムアウトと timeout 再試行に当たる
- Suggestion: `retry_on_timeout` と条件付き書き込みの組み合わせ(再送で 409 になりうる)
- Suggestion: opensearch ロガーを DEBUG にすると本文・応答がログに出る(R9)
- Nitpick: `SecretRedactionFilter.filter` が `getMessage()` の例外を伝播する
- Nitpick: `redact_url_credentials` の port 参照(不正ポート、port=0)
- Nitpick: 設定値どうしの整合を検証していない
- 確認済み: opensearch-py 3.2.0 の実呼び出しで `if_seq_no`/`if_primary_term`、`op_type=create`、`conflicts=proceed`、`retry_on_conflict` のリクエスト形が正しいこと。§4 仮値と config の一致。依存ルールの許可表と module v0.3 R1〜R5 の一致

### test-reviewer(Critical なし、Important 2 件)
- **Important**: fake にスレッド安全性がなく、P4 の Gate 併用テストが flaky になり得る
- **Important**: フック・差し替えがキー(文書ID)指定できず、P2 のバッチ内「特定の1文書だけ失敗」を書きにくい
- Suggestion/Nitpick: R6〜R8 の部分検査、実クライアントの transport 差し替えによるリクエスト形テスト、全体異常の配線テスト、分類器の固定、fake 自己テストの穴、config テストの環境依存・既定値網羅・下限、依存ルール検査器の正例・検出形式・違反理由、その他 Nitpick

## 指摘対応(code-implementer。メインが検証を再実行して確認)

検証: `uv run pytest` → **433 passed**(修正前 253)。`ruff check` 全通過、`ruff format --check` 58 files already formatted。実装担当は5回連続実行で不安定さがないこと、`InMemorySearchIndex` のロックを一時的に no-op にすると並行 replace のテストが失敗することも確認済み。

| # | 内容 | 対応 |
| --- | --- | --- |
| 1 | fake のスレッド安全性 | 対応。各操作本体を RLock で囲み、フック・Gate はロック外で実行。`FakeBehavior` の取り出しも原子化。並行 replace・8スレッドのフック消費・フック中のブロックが他スレッドを止めないことの自己テストを追加 |
| 2 | フック・差し替えのキー指定 | 対応。`before(op, cb, *, key=None)` / `inject(op, outcome, *, key=None, times=1)`。別キーでは消費されず残る |
| 3 | 401/403 | 対応。全体異常 `OpenSearchUnavailableError`(reason `http_401`/`http_403`)。error_type 判定が先なので既存 reason は不変 |
| 4 | log_masking | 対応。整形失敗は固定文言 `UNFORMATTABLE_MESSAGE` に置換(元の args は出さない)。port は `is not None` 判定、不正ポートは捕捉 |
| 5 | R6/R7/R8 部分検査 | 対応。R8: 409系で client 呼び出しが1回。R6: 抽象メソッド集合の固定。R7: AST で書き込み呼び出しの場所を固定(`client_calls.py` と `search_index_adapter.py` のみ)、検索インデックスの全書き込みが条件付きであることを確認 |
| 6 | 実クライアントの transport 差し替え | 対応。`test_request_shape.py`(create/replace/update/delete/delete_by_query/count/search/refresh/store/IDのURLエンコード) |
| 7 | 全体異常の配線 | 対応。全メソッド × (ConnectionTimeout, 503)。メタテストでメソッド一覧が抽象メソッド集合と一致することを確認 |
| 8 | 分類器の固定 | 対応。401/403、SSLError、非intステータス、`OpenSearchUnexpectedResponseError` |
| 9 | fake 自己テスト補強 | 対応。削除フック、ABA、`delete_by_query` の他書き手削除、last_seen_at 無し→Updated、primary_term 違い、フックのFIFO・順序、`calls` の key。`count_existing_ids` はID重複なし前提を docstring に明記、チャンク境界(1/999/1000/1001/2000)テスト |
| 10 | config テスト | 対応。環境変数のクリア fixture、既定値の表駆動(§4)、下限、全 int/float フィールドが `le` を持ち `UPPER_BOUNDS` と一致するメタテスト |
| 11 | 依存ルールテスト | 対応。正例15経路、import 形式の検出、負例追加、違反パス・理由まで確認。動的 import 非対応は docstring に明記 |
| 12 | Nitpick | 対応(全件) |

## 見送り・後続フェーズへ送る事項

- `delete_by_query` 専用の長いタイムアウト(クライアント30秒+timeout再試行で同一削除が重複発行されうる。収束はするが無駄が多い) → **P4 で対応**
- opensearch ロガーを WARNING 以上に固定(DEBUG で本文・応答が出る) → **P5 で対応**。P5 のログ検査テストでセンチネル文字列が出ないことを確認する
- `retry_on_timeout` で書き込みを再送すると、1回目が成功済みの場合 `op_type=create`/`if_seq_no` 付き PUT が409になりうる。データは壊れないが `created`/`updated` の区分が変わりうる → **P2 の登録テストで、409→読み直しで成立することを確認する**
- 設定値どうしの整合検証(`retry_backoff_max < initial`、`max_raw_bytes > max_batch_bytes` など) → 今回は見送り(既定値では実害なし)。必要なら P5 で検討
- `redact_url_credentials` で `urlsplit` 自体が投げる ValueError(不正なIPv6括弧など)は未捕捉(指摘外、P5 の起動ログ利用時に再確認)
- U-31 の実機確認は持ち越し(変更なし)。fake の `Instant.parse` がオフセット付き表記を受理する点などは実機より寛容な可能性がある

## 未対応事項

- 再レビュー(下記)の結果待ち
- コミット未実施

## 次のアクション

1. 再レビュー: test-reviewer(Important 2件の解消確認と追加テスト)、code-reviewer(分類・log_masking の変更)
2. 指摘なし/解消済みを確認後、P2(documents + lifecycle の最小部分)へ

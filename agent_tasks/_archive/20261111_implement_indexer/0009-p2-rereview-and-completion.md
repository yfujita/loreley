# 0009 P2 再レビューと完了

日付: 2026-11-11 / 対象: 0008 の修正後の P2 / レビュー: code-reviewer、test-reviewer(再レビュー)
比較基準: HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)

## 再レビュー結果

### code-reviewer(可。新たな Critical/Important なし)
- A1(メンテナンス中の LLM 再生成)= 解消。pending と確認した後・LLM 呼び出し前にフラグを確認し、書き込み前の確認も残る
- A2(再試行が時間方向に無制限)= 実質解消(要承認)。間隔 60→120→240→480→600…、成果は「走査間に WRITTEN が1件以上」、起動時の最初の走査は即時、状態の読み書きは単一ロック配下でデッドロックなし。ただし `pending` が直らない限り最長1時間間隔で永久に再走査・再生成する(`failed` 未実装の下ではやむを得ない妥協。K54(3) の「上限付き」を完全には満たさない)
- A3(孤立サロゲート)= 解消。検査は oversize 後・抽出前。固定メッセージで `from None`
- 前回 Suggestion: last_seen_at のミリ秒比較、停止での試行打ち切り、PDF 打ち切り、正規化の高速化 = 解消。文字コード判定は部分的に解消(EUC-JP は不可避と docstring に明記)
- 実測確認: 正規表現と `unicodedata` を全 0x110000 コードポイントで突き合わせ不一致0。PDF の早期打ち切りは全ページ処理と同一結果(接頭辞性)。CP932 で PUA になるのはリード F0〜F9・単独バイト A0/FD〜FF のみで、正当な UTF-8 日本語・CP932(①㈱髙・半角カナ)は弾かれない
- ユーザー未承認の追加(0008 の6項目)はいずれも妥当
- Suggestion S1: プラン §3 案12(再走査は「書き戻し失敗後に間隔下限つきで1回」)・§4 の表と実装(成果がない限り指数バックオフで最長1時間間隔の永続再走査、新設定 `summary_rescan_max_interval_seconds`)が乖離。**方針変更に当たるためユーザー承認が必要**。承認後にプラン更新(案12の差し替えと §4 の行追加)の作業記録を残す
- Suggestion S2: PAUSED も成果なしとして間隔が伸びるため、長いメンテナンス後に最悪1時間 pending が放置される(新規登録分はキュー経由で即時なので影響は既存 pending のみ)。README に書けば十分
- Nitpick: N1 LLM のリトライ前にメンテナンスを再確認しない(窓は最大2呼び出し、書き込み前確認が残る)/ N2 PDF の再正規化の最悪ケース(悪意ある入力限定)/ N3 PUA 判定が文字ごとの Python ループ(正規表現にすれば高速。任意)

### test-reviewer(Critical/Important なし。信頼度「十分」)
- 前回 Important I1〜I4 = すべて解消。レビュアーがスクラッチ上で改変して各テストが失敗することを確認(`_body_is_unchanged` を content_hash のみに、`_rescan_if_needed` の try/except 除去、pypdf ロガー抑止除去・ワーカーが例外メッセージを出す、`notify_all()` 除去)
- 新機能(A1 の3経路、A2 の倍率・上限・リセット、A3、ミリ秒比較、should_stop、BOM・私用領域、正規化)のテストは十分。約70通りのミューテーションで重要な退行はすべて検出
- 実行: 863 passed を3回、高負荷(8並列+CPU負荷)で8回、いずれも不安定さなし
- Suggestion S1: PDF 打ち切りの境界(正規化後がちょうど上限で後続ページあり)が未固定(`>` を `>=` にしても通る。`pdf_with_pages(["x"*1024, "y"])` は `truncated is True`、`pdf_with_pages(["x"*1024])` は `truncated is False` を追加)
- Suggestion S2: 本番配線「停止要請でバックオフの待ちを打ち切る」(`sleep=stop_event.wait`)が未検証(`retry_backoff_initial_seconds` を30などに上げ、`run_once()` の経過が5秒未満であることを確認。processor 単体の `sleeps == [1.0]` は緩める)
- Suggestion S3: `submit` の `notify()` が未検証(`_SignalingCondition` を再利用し、待ちに入ったことを確認してから submit、`take(wait_seconds=30.0)` が5秒未満で返ること)
- Nitpick: N1 UTF-32 の BOM 個別エントリは UTF-16 の BOM と冗長/他の経路で None になるためテストが効いていない(コメントで冗長と明記するか削除)、N2 実装内部名への結合は許容、N3 件数ヘルパの重複と test_registration.py(1059行)の規模、N4 時間条件の assert の余裕

## 判断

- P2 は完了。Important はすべて解消済み
- Suggestion(test-reviewer の S1〜S3)は**P3 の実装依頼の先頭項目として組み込む**(再レビューの往復を増やさないため)。N1〜N4 と code-reviewer の S2・N1〜N3 は持ち越し(必須ではない)。S2 は README(P6)に記載する
- code-reviewer S1(案12からの方針変更)は**ユーザー承認待ち**。承認が得られたらプラン更新の作業記録を残す。承認前に P3 以降へ進めるのは、再走査の挙動が `crawl_runs` に影響しないため問題ないと判断した

## 検証結果(メインが再実行して確認、0008 時点)

- `uv run pytest` → 863 passed(3回連続)、`ruff check` 全通過、`ruff format --check` 117 files already formatted

## 持ち越し・後続フェーズへ送る事項

- P3 の先頭で test-reviewer の S1〜S3 を追加する
- P5: 0007・0008 の申し送り(base64 のデコード前サイズ判定、日時パース、JSON 写像、lone surrogate の 400、他の文字列フィールドの形式検証、pypdf ロガーの設定整理)
- P6: README に、要約入力が先頭 `summary_input_max_chars`(既定30,000)文字までの仮値、メンテナンス解除後の再開が最悪で `summary_rescan_max_interval_seconds` 遅れうること、小要素が大量の HTML の処理時間(約40秒)を記載
- ユーザー確認が必要な事項(完了報告時に確認): 0007 判断8・12・17、0008 の6項目、code-reviewer S1(案12からの方針変更)
- U-31(実機)、`document_id`(先頭 `/` を除かない)の Crawler 側突き合わせ、docs への新設定の反映は持ち越し
- コミット未実施

## 次のアクション

P3(crawl_runs / lifecycle)を `code-implementer` に依頼する(0002 §6 P3。申し送りは 0006・0007・0008 と本記録)。

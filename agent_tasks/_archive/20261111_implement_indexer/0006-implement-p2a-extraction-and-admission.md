# 0006 P2a 実装: ID算出・extraction・lifecycle の最小部分

日付: 2026-11-11 / 実施: code-implementer(メインが検証を再実行) / プラン: 0002 §6 P2 の前半
比較基準(P2 全体のレビュー用): HEAD c065b9e(`apps/indexer` は未コミットの新規ファイル全体)
レビューは P2 全体(P2a+P2b)の完了後に1回実施する

## 実施内容の概要

`document_id` 算出、extraction(txt/Markdown/HTML/PDF)、lifecycle の最小部分(`deletion` / `deletion_result` レコードモデルと受理条件の照会)、契約エラー、抽出用の設定変換を実装した。登録・last-seen・summarization・通知・deletion・api・main は未着手(P2b 以降)。コミットはしていない。

## 検証結果(メインが再実行して一致を確認)

- `uv run pytest` → **605 passed**(P1 の 450 から +155。実装担当は3回連続で同数を確認)
- `uv run ruff check` → All checks passed
- `uv run ruff format --check` → 83 files already formatted

## 変更・作成したファイル(`apps/indexer/` 配下)

- 依存: `pyproject.toml` に beautifulsoup4(>=4.15,<5)、lxml(>=6.1,<7)、pypdf(>=7.0,<8)を追加。`uv.lock` 更新
- `src/loreley_indexer/common/errors.py`: `ContractError`(`status_code`/`code`/`message`/`retryable`)、`AdmissionRejectedError`(409)と 5 種(`CrawlNotStartedError`、`CrawlSourceMismatchError`、`CrawlStartedAtMismatchError`、`CrawlAlreadyClosedError`、`CrawlFinishedError`)
- `src/loreley_indexer/config.py`: `Settings.extraction_config()` → `ExtractionConfig(max_content_bytes)`
- `src/loreley_indexer/documents/`: `document_id.py`(`compute_document_id`、`normalize_external_id`)、`extraction/`(`extractor.py`、`results.py`、`decoding.py`、`html.py`、`pdf.py`、`normalization.py`)
- `src/loreley_indexer/crawl_runs/`: `__init__.py`(`Admission`、`AdmissionChecker` を再公開)、`lifecycle/{__init__,records,admission}.py`
- `tests/`: `documents/test_document_id.py`、`documents/extraction/{samples,test_extractor,test_normalization}.py`、`crawl_runs/factories.py`、`crawl_runs/lifecycle/{test_records,test_admission}.py`、`common/test_errors.py`、`test_config.py`、`architecture/{dependency_rules,test_dependency_rules}.py` の更新

## 判断・設計上の理由(倒した未決・仮定)

1. **`document_id` の正規化**: NFC → `\` を `/` に統一 → **先頭 `/` の除去**(実装担当は「先頭に `/` を付けない」を正規化規則と読んだ)。`source_id` は正規化しない。NUL を含む `source_id`/`external_id` は ValueError(P5 で 400 に変換)。テストベクタは api 4.3 の例と一致
   - **メイン判断(P2b で修正)**: 設計書(api 4.3、arch)の文言は「NFC に正規化し、パス区切りを `/` に統一する(ルートからの相対パス、先頭に `/` を付けない)」で、後半は入力の前提を述べており、Indexer が除去する規則とは書かれていない。`last-seen` は Crawler が算出した `document_ids` を受けるため、Indexer だけが除去すると ID がずれる恐れがある。よって**先頭 `/` は除去しない**側に倒す(NFC と区切り統一のみ)。P2b の修正項目とし、テストを更新する。Crawler 側の実装時に突き合わせる事項として持ち越しに記録する
2. 正規化の順序: 改行統一 → 制御文字除去 → NFC → 行末空白除去 → 空行圧縮
3. 正規化の規則: 空行3個以上を2個に。空白だけの行も空行扱い。行末空白は `str.rstrip()`(NBSP・全角空白を含む)。制御文字は Unicode Cc(C1 を含む)。**サロゲート(Cs)も除去**(設計書にない追加。PDF 抽出の孤立サロゲートで UTF-8 化できず `text_hash` が計算できなくなるのを避ける)
4. HTML: 要素の境界ごとに `\n` を入れて `get_text`(`<p>a</p><p>b</p>` の連結防止)。除去は script・style のみ(コメントは bs4 が除く)。`<title>` の文字列は本文に含まれる
5. PDF: `is_encrypted` なら空パスワードで読めても `ENCRYPTED_PDF`。構文解析部分のみ `Exception` を捕捉して `CORRUPT_DOCUMENT`。本文が空(スキャンPDF等)は失敗でなく成功(空の content と空文字列の `text_hash`)。pypdf は警告に原本の一部(ヘッダのバイト列)を出すため、R9 に沿って `pypdf` ロガーを CRITICAL に固定(`pdf.py` の import 時のグローバル設定)
6. 失敗種別(仮名): `unsupported_mime_type`、`undecodable_text`、`encrypted_pdf`、`corrupt_document`。HTML の `ParserRejectedMarkup` は `corrupt_document`
7. 文字コードの既知の限界: Python の cp932 は 0x80、0xA0、0xFD〜0xFF も私用領域/C1 の文字に変換するため、UTF-16 など別の文字コードが失敗にならず文字化けした本文として成功する場合がある(プラン項目13のまま。対策なし)
8. 切り詰め: UTF-8 バイト上限を文字境界(継続バイトを戻る)で切る。正規化後に判定(正規化で上限内に収まれば `truncated=false`)。`text_hash` は切り詰め後本文から計算
9. レコードモデル: `DeletionRecord`(`deletion-{source_id}`)、`DeletionResultRecord`(`deletion_result-{crawl_id}`)。`to_body()`/`from_body()` で往復。日時は UTC ミリ秒文字列で保存。値のない項目は保存しない(置き換え書き込みで ID 一覧が消え `finish_request_digest` が残る K35 の挙動を使う。空リストと「なし」は区別)。**設計書にない項目を3つ追加**: `crawl_id`(待ち行列の順序・検索用)、`reason_detail`(`delete_error` のエラー種別。plan §3.1 の「詳細項目に種別」)、`started_at`/`ended_at`。`reason` は `DeletionReason`(failed 5種、discarded 2種、validation_failed 3種。plan §3.1)。不正な保存記録は `MalformedRecordError`(項目名のみ。api で 500)。終端遷移ヘルパーは P3
10. 受理条件の照会: `AdmissionChecker(StoreReader).check(source_id=, crawl_id=, crawl_started_at=) -> Admission(rewrite_mode)`。判定順は 結果なし → source_id → crawl_started_at → status が `running` → `finish_received_at` なし(arch 9.5 の条件順)。`failed`/`cancelled` の終了通知後は条件4で `crawl_already_closed`(D-82(4))。`crawl_started_at` はミリ秒UTCに正規化して比較(秒精度・µs付き・オフセット付きでも一致すれば受理。D-79(c) は設計上未決のため寛容側に倒した)。読み取り専用の `StoreReader` のみ受け取る(R6)。ロック所有(条件6)は文書ごと(P2b)
11. 依存ルールの許可表: `ALLOWED["config"]` に `documents.extraction` を追加(config.py が各モジュールの設定 dataclass に値を詰めるため。extraction は葉で循環なし)。この1行のみ

## arch テストID対応表(P2a の範囲)

| arch ID | 内容 | テスト |
| --- | --- | --- |
| S-7 | txt・Markdown・HTML・PDF、UTF-8・BOM・CP932 | `test_extractor.py` |
| E-5 | 抽出失敗は結果で返る(登録での `extract_failed` 書き込みは P2b) | `test_extractor.py`(undecodable、corrupt_pdf、encrypted_pdf、unknown_mime_type) |
| E-6 | 上限超過で切り詰め `truncated=true` | `test_extractor.py`、`test_normalization.py` |
| E-45(抽出側) | `ExtractionFailed` は `text`・`text_hash` を持たない | `test_failed_result_carries_no_text_or_hash` |
| C-12 / C-3(部分) | `text_hash` の決定性、本文変更で変わる | `test_extractor.py`(text_hash_*) |
| D-77 / D-78 / D-81 | 不一致・未開始・終端状態の拒否(1件も書かない) | `test_admission.py` |
| D-82(1)(2)(4) | 終了通知受理後 `crawl_finished`、failed/cancelled は `crawl_already_closed` | `test_admission.py` |
| C-27(a)(b) の取得元 | `rewrite_mode` を受理条件の確認から返す(バッチ間の適用は P2b) | `test_rewrite_mode_comes_from_the_copied_deletion_result` |
| C-26(部分) | 表記違いの `crawl_started_at` を同一時刻として扱う | `test_admission.py` |

P2b 以降: C-1〜C-2、C-4〜C-7、C-10、C-15、C-17〜C-25、E-20、E-30、E-41、E-44〜E-45b、L-5、L-9

## 未対応事項・持ち越し

- 原本サイズ超過(`oversize`)、ロック所有確認(`lock_not_owned`)は P2b
- 受理条件の拒否 409 の共通エラー形式への変換は P5。`ratio_threshold` の NaN/Inf の形式不正拒否は P5
- pypdf のログ抑制は import 時のグローバル設定 → P5 のログ検査でも確認
- 日本語 PDF の抽出品質は未検証(プラン持ち越し6)
- `document_id` の先頭 `/` の扱いを Crawler 側実装時に突き合わせる(上記 判断1)

## 次のアクション

P2b(登録・last-seen・summarization)を `code-implementer` に依頼する。申し送り: 0006 の公開インターフェース(`compute_document_id`、`TextExtractor`、`AdmissionChecker`、レコード)、P1 の fake と 0005 の持ち越し(タイムアウト再送で409になる場合の読み直しテスト)、判断1の修正(先頭 `/` を除去しない)。

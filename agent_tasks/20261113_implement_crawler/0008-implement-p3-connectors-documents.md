# 0008 P3: `connectors`(interface・filesystem・レジストリ)と `documents`

日付: 2026-11-14 / 実施: code-implementer / 記録・再検証: メインエージェント
フェーズ開始時点の HEAD: `061dc7b196f67a689e0d834eb676ce356d6cdb34`(`apps/crawler/` は未コミット。P3 のレビュー対象は P3 で追加・変更したファイル)

## 1. 検証結果(メインが再実行、`apps/crawler`)

```
$ uv run pytest -q           -> 1395 passed, 3 skipped in 10.07s(P2 後の 914 + 481)
$ uv run ruff check          -> All checks passed!
$ uv run ruff format --check -> 125 files already formatted
$ uv lock --check            -> Resolved 39 packages
```

skip 3件(macOS・uid 501): `tests/connectors/filesystem/test_characters.py` の 非UTF-8名の `surrogateescape`、大文字小文字だけが違う名前、NFC/NFD の併存。理由は skip メッセージに記載(macOS APFS は作成できない)。権限エラーのテスト(#4・#12・#16 の実権限版)は uid 501 で実行され通る(root では `skip_if_root`)。`apps/indexer`・docs・infra への変更なし。`git status` は `apps/crawler/` のみ。

実装担当による Linux 相当の確認(Docker 20.10.13。`python:3.12-slim-bookworm`、リポジトリは `:ro` でマウントしコンテナ内の `/tmp` にコピー): 非 root(uid 1000)で `tests/connectors tests/documents tests/architecture` が **742 passed, 0 skipped**(Linux 専用テストを含む)、root で 737 passed・5 skipped(権限エラーのみ)。メインがコンテナ・プロセスの残りがないことを確認。

## 2. 実装内容(`apps/crawler/src/loreley_crawler/`)

- `connectors/interface/`: `ConnectorType`・`Connector`・`EnumerationStream`(`next` は `DocumentRef` か `Completed`。`StopIteration` を完了に使わない)、frozen データクラス(`DocumentRef`・`FetchedDocument`・`DocumentMetadata`・`Completed`)、`ConnectorError(category, scope, retry, message)`+`ConnectorError.of(...)`(interface 6.2 の表から scope/retry を補う。内部エラーだけ scope 必須)、`to_connector_error`・`converting_unexpected_errors`(想定外の例外を `connector_internal_error` に)
- `connectors/filesystem/`: FS 設計書2〜9章。`fs_ops.py`(`FsOps`・`OsFsOps`・`FileStat`・`DirEntryLike`。読み取り操作のみ)、`settings.py`、`config.py`(設定検証)、`patterns.py`(glob)、`paths.py`、`errors.py`(errno と分類)、`enumeration.py`、`fetch.py`、`connector.py`(`FileSystemConnectorType(fs_ops=None, settings=None)`)
- `connectors/registry.py`: `ConnectorRegistry`(`file_system` のみ登録。保護ラッパで `validate_config`・`create` の想定外の例外を `connector_internal_error`(source)に変換)、`create_connector_registry(...)`、`find()`(未登録は None)。`connectors/__init__.py` は docstring のみ
- `documents/`: `identifiers.py`、`document_id.py`(`compute_document_id`)、`enumeration.py`、`fetching.py`、`settings.py`、`errors.py`
- tests: `tests/documents/document_id_vectors.json`(interface 5.2 の全行、出典つき)、`tests/fakes/fake_connector.py`・`fake_fs_ops.py`(`ScriptedFsOps`)、`tests/unicode_samples.py`、`tests/connectors/`・`tests/documents/` のテスト一式
- `tests/architecture/` の許可表・R7 検査は変更不要(P1 で必要な行が用意済み。P2 の「全辺固定」の期待集合も不変)

## 3. 決めてよい事項で決めた内容

- **`documents` の API(P6 `crawl` が使う)**
  - `DocumentEnumeration(stream, source_id=, settings=)`: `next()` は `EnumeratedDocument(document_id, external_id(最終形), ref)` か `InvalidExternalId(error, display_external_id)` か `Completed`。重複は飛ばす。失敗は例外(`ConnectorError` の `external_id_collision`、列挙の失敗、`connector_internal_error`(source)、専用の `EnumerationTooLargeError`(`max_enumerated_documents` 超過。`ConnectorError` ではなく `CrawlerError` の子。architecture の `enumeration_too_large` 用))。失敗後の `next()` は同じ例外を再送出(失敗を完了と取り違えない)。`enumerated_count`、`has_enumerated(document_id)`、`close()`(stream だけ閉じる)。衝突の説明文は「切り詰めた external_id と document_id」(CA-P-45)で値そのものは載せない
  - `DocumentFetcher(connector, settings=).fetch(ref) -> PreparedDocument(content, content_hash, size, metadata)`: `size_hint` が上限超なら読まずに `oversize`。Connector が上限超の原本を返した場合も防御として `oversize`。`title`・`path`・`url`・`mime_type` の孤立サロゲートは表示用に置換
  - `DocumentsSettings(max_raw_bytes=20MiB, max_enumerated_documents=500,000, display_max_chars=200)`: architecture 11章の仮値。`config.py`(P8)が詰める
- **`compute_document_id`**: Indexer と同じく NFC と `\`→`/` を内部で適用(冪等)。テストベクタの「NFD でも同じ」「`a\b.txt` と `a/b.txt` が同じ」の行が算出関数への直接入力で成立する必要があるため。NUL と孤立サロゲートは `ValueError`(入力値は含めない)
- **`connector_internal_error` の説明文**は例外の型名(と `OSError` なら errno 名)のみ(メッセージはパスや設定値を含みうるため)
- エラーの説明文は日本語の固定文(FS 設計書 7.3 の例示に合わせる)。FS の設定違反は項目名(配列は添字)と違反の種類だけで、入力値・未知キーの名前は載せない
- **FS エンコーディングの確認(CFS-P-22、CFS-U-4 の「実装時に決める」範囲)**: `create` で `FsOps.filesystem_encoding()` が UTF-8 であることを確認し、違えば `connector_internal_error`(source)
- **`FsOps`**: 設計書の疑似コードの呼び出し+`filesystem_encoding()`。`stat`・`fstat` は自前の `FileStat(mode, size, mtime_ns, device, inode)`(偽が組み立てやすい)。読み取り操作のみ
- **`FileSystemSettings`**(仮値・設定可能): パターン100件・1024バイト、読み取り単位1MiB、説明文のパス200文字
- **FS の列挙**: ジェネレータ。失敗後の `next()` は同じ例外を再送出。`close()` の後の `next()` は `RuntimeError`
- **ruff format の挙動への対処**: ruff 0.17.5 は `\uXXXX` を実際の文字に書き換えるため、結合文字・U+FFFD は `chr()` 定数(`tests/unicode_samples.py`、`documents/identifiers.py` の `REPLACEMENT_CHARACTER`)で組み立て。JSON のテストベクタは `\u` 表記
- **`ScriptedFsOps`**: 実 FS(一時ディレクトリ)への呼び出しに、操作ごとのフック(`before`)と応答・例外の差し替え(`inject`)を足す。#13・#15・#17 を決定的に書くための注入点。`virtual_root` で `/` を一時ディレクトリに読み替え、`root=/` のテストを実際の `/` を走査せずに行える

## 4. 検証項目との対応

- FS 設計書10章 #1〜#23: `tests/connectors/filesystem/` の各テスト。interface 10章の契約テスト: `tests/connectors/test_connector_contract.py`(FS と偽 Connector の両方に同じテスト)と `tests/documents/`。#13・#15・#17 は `ScriptedFsOps` で決定的。スレッド・スリープなし
- `document_id` テストベクタ: interface 5.2 の全8行(10入力)で一致。共通処理を通さない行(先頭が `/`)は、共通処理に通すと `invalid_external_id` になることも確認。全行が Indexer の `compute_document_id` の出力と一致することを使い捨てスクリプトで確認(Indexer は無変更)
- 変異確認(scratchpad のコピーで73件)。当初3件が生き残り(`is_inside` の前方一致・`join_path` が `//` を作る・stat 上ファイルのルートの受理)、テストを追加して全件検出

## 5. 設計書との食い違い・不明点

食い違いはない。注意点:

1. FS 設計書 5.4 は日時変換の例外として `ValueError`・`OverflowError` の両方を挙げるが、`epoch + timedelta(microseconds=ns//1000)` で実際に出るのは `OverflowError` のみ(`ValueError` の分岐は自然には起きず単独テストは作れない。年0・10000・巨大値の3ケースで固定値化を検証)
2. FS 設計書 4.2 のとおり取得時のリンク検査は最後の構成要素だけで、`locator` の途中のディレクトリリンクは取得できてしまう。許容された挙動で、変わったとき気づけるようテストで固定
3. `invalid_external_id` の文書が同じ列挙で2回返された場合は重複除去できず2回報告する(`document_id` を持たないため)。FS では起きず、Web Connector 追加時に再検討が必要(提案のみ)

## 6. P6 への申し送り

- `documents` の API(§3)と `EnumerationTooLargeError`(`failed(enumeration_too_large)`)
- `external_id_collision` は `DocumentEnumeration.next()` が `ConnectorError` で送出。`failed` にする判断は `crawl`
- `invalid_external_id` は例外ではなく `InvalidExternalId` で返る(`warnings`・`invalid_id_count` 用)
- レジストリは `ConnectorRegistry.find()`(未登録は None)
- 偽 Connector・`ScriptedFsOps` は `tests/fakes/` を使う

## 7. 持ち越し(実機でしか確認できない。CFS-U-4)

- 実際の NFS/SMB・Docker バインドマウントでのマウント外れの errno と症状、集合 T の妥当性、`st_ino` の信頼性、ブロッキング I/O 中のスレッド挙動
- コンテナ内 Python のファイルシステムエンコーディング(`python:3.12-slim-bookworm` では UTF-8。実運用イメージでは未確認)、`:ro` マウント

## 8. 設計書の改版依頼リストに載せる候補(提案)

- `DocumentEnumeration` が返す3種の結果(`EnumeratedDocument`・`InvalidExternalId`・`Completed`)と `EnumerationTooLargeError`
- FS エンコーディングの確認を `FsOps` 経由で `create` に置いたこと(CFS-P-22 の選択)

## 9. 次のアクション

1. P3 の code-reviewer + test-reviewer を並列実施(重点: FS の errno 分類・`FsOps`、`document_id`、列挙の終端(失敗後に `Completed` を返さない)、取得の `oversize` の分岐、ログ・説明文に値や本文が出ないこと、テストが設計書10章の番号を検証していること)
2. 指摘対応・再レビュー → 0009 に記録
3. P4(`sources`・`jobs/records`・`jobs/locks`)。**0007 §4 の申し送りを必ず依頼に含める**

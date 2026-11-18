# 結合テスト用のサンプル文書

`tests/integration/crawler/` のテストが、検索対象のディレクトリ(`tests/integration/crawler/data/<source_id>/`。
コンテナ内では `/data/documents/<source_id>`)へコピーする固定のファイル。Crawler の FileSystem Connector が
これを列挙・取得し、Indexer が抽出して索引する。

Indexer の結合テスト(`tests/integration/indexer/samples/`)の `sample.{txt,md,html,pdf}` と同じ内容の複製。
モジュール間でファイルを共有せず、それぞれが自分のサンプルを持つ(片方の変更が他方のテストを壊さないため)。
Crawler の結合テストは抽出結果の詳細(Indexer の IT-10・IT-11 の範囲)を再確認せず、
**検索用の語が本文として命中すること**だけを確認する。

| ファイル | 取り込まれるか | 理由・期待 |
| --- | --- | --- |
| `sample.txt` | 取り込まれる | 既定の拡張子 `.txt`。検索用の語は `txtmarkeralpha` |
| `sample.md` | 取り込まれる | 既定の拡張子 `.md`。検索用の語は `mdmarkerbeta` |
| `sample.html` | 取り込まれる | 既定の拡張子 `.html`。検索用の語は `htmlmarkergamma` |
| `sample.pdf` | 取り込まれる | 既定の拡張子 `.pdf`。ASCII テキストの 1 ページ PDF。検索用の語は `pdfmarkerdelta` |
| `nested/sample-nested.txt` | 取り込まれる | サブディレクトリの再帰列挙の確認。外部 ID は相対パス `nested/sample-nested.txt`。検索用の語は `nestedmarkerepsilon` |
| `ignored.csv` | **取り込まれない** | `.csv` は既定の拡張子(`.txt`・`.md`・`.markdown`・`.html`・`.htm`・`.pdf`)にない(FS 設計書 CFS-K-3) |
| `.hidden.txt` | **取り込まれない** | 隠しファイル。`include_hidden` の既定は `false` |

取り込まれるのは 5 件(`sample.txt`・`sample.md`・`sample.html`・`sample.pdf`・`nested/sample-nested.txt`)で、
これがクロールの `enumerated_count` の期待値になる。取り込まれない 2 件は、
`csvignoredmarker`・`hiddenignoredmarker` が検索で命中しないことで確認する。

サイズ超過のファイル(Crawler の `MAX_RAW_BYTES=65536` を超える 70,000 バイト)は、容量を避けるため
ここには置かず、テストが実行時に生成する。

## ファイルの権限

Crawler のコンテナは uid 10001 で動く。ホストの所有者と異なるので、テストは、コピーするファイルを 0644、
ディレクトリを 0755(others が読める権限)にして置く(`support.py` の `SourceDirectory`)。
このディレクトリのファイルも 0644(ディレクトリは 0755)にしておくこと。

## `sample.pdf` の生成方法

`tests/integration/indexer/samples/README.md` の標準ライブラリだけのスクリプトと同じ。

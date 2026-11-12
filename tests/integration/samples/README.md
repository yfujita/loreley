# 結合テスト用のサンプル文書

`tests/integration/` のテストが、Crawler 役として Indexer に登録する固定の原本。
期待する抽出結果の要点は次のとおり(テストの期待値と対応する。IT-10・IT-11)。

| ファイル | MIME タイプ | 期待する抽出結果 |
| --- | --- | --- |
| `sample.txt` | `text/plain` | 原文のまま本文になる(UTF-8、LF、行末空白なし、NFC。正規化で変わらないので `content` が原文と完全一致する)。検索用の語は `txtmarkeralpha` |
| `sample.md` | `text/markdown` | Markdown の記法を解釈せず、原文のまま本文になる(`#` や `**` が残る)。検索用の語は `mdmarkerbeta` |
| `sample.html` | `text/html` | タグ、`<script>`、`<style>` が本文に残らない。段落の境界は改行になり、語が連結しない。検索用の語は `htmlmarkergamma`。本文に残ってはいけない語は `scriptleakmarker`・`cssleakmarker` |
| `sample.pdf` | `application/pdf` | pypdf で ASCII テキストを抽出できる 1 ページの最小 PDF。検索用の語は `pdfmarkerdelta`(日本語 PDF の抽出品質は未検証のため、日本語は使わない) |
| `corrupt.pdf` | `application/pdf` | PDF ではないバイト列。抽出に失敗し、`extract_failed: true` で登録される(本文なし) |

## `sample.pdf` の生成方法

標準ライブラリだけで作れる(外部ツール不要)。バイト列を変えたいときは、下のスクリプトを
`python make_pdf.py > sample.pdf` で実行して置き換える。xref のオフセットを正しく計算しているので、
pypdf が警告なしに読める。

```python
"""最小の 1 ページ PDF(Helvetica、ASCII テキスト)を標準ライブラリだけで生成する。"""

import sys

text = "Hello Loreley PDF. This page checks the PDF extraction. pdfmarkerdelta"
stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
]
out = bytearray(b"%PDF-1.4\n")
offsets = []
for number, body in enumerate(objects, start=1):
    offsets.append(len(out))
    out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
xref_offset = len(out)
out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
for offset in offsets:
    out += b"%010d 00000 n \n" % offset
out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_offset)
sys.stdout.buffer.write(out)
```

`corrupt.pdf` は、`printf` などで書いた平文(PDF のヘッダを持たない)でよい。

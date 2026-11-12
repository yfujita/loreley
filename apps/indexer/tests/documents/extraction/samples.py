"""抽出テスト用の原本サンプル。PDF は ASCII の最小構成で、追加の生成ライブラリを使わない。"""

import io

from pypdf import PdfReader, PdfWriter


def minimal_pdf(text: str) -> bytes:
    """標準フォントで `text` を 1 行描く 1 ページの PDF。`text` は ASCII で `()\\` を含まない。"""
    return pdf_with_pages([text])


def pdf_with_pages(page_texts: list[str]) -> bytes:
    """ページごとに標準フォントで 1 行描く PDF。各 `text` は ASCII で `()\\` を含まない。"""
    page_count = len(page_texts)
    font_number = 3 + 2 * page_count
    kids = " ".join(f"{3 + 2 * index} 0 R" for index in range(page_count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii"),
    ]
    for index, text in enumerate(page_texts):
        stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * index} 0 R"
            f" /Resources << /Font << /F1 {font_number} 0 R >> >> >>".encode("ascii")
        )
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    body = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n" % number + content + b"\nendobj\n"
    xref_offset = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        body += b"%010d 00000 n \n" % offset
    body += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_offset,
    )
    return bytes(body)


def encrypted_pdf(text: str, *, user_password: str = "user-password") -> bytes:
    """`minimal_pdf` を RC4 で暗号化したもの(AES は追加ライブラリが要るため使わない)。

    `user_password` が空なら、開くのにパスワードは要らない(編集・印刷などを制限する所有者
    パスワードだけの暗号化)。
    """
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(minimal_pdf(text))))
    writer.encrypt(user_password, owner_password="owner-password", algorithm="RC4-128")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()

"""テストで使う、見た目が紛らわしい文字列。

結合文字をソースに直接書くと、エディタ・フォーマッタが合成した文字と見分けがつかず(`\\u` の
エスケープは、フォーマッタが文字そのものに書き換えることがある)、NFC と NFD の違いを意図した
テストが読めなくなる。`chr` で組み立てて、どちらの形かをコードに残す。
"""

COMBINING_ACUTE_ACCENT = chr(0x0301)
COMBINING_VOICED_SOUND_MARK = chr(0x3099)

# 「が」「ぎ」。NFC は 1 文字(U+304C・U+304E)、NFD は「か」「き」+ 濁点の 2 文字。
GA_NFC = chr(0x304C)
GI_NFC = chr(0x304E)
GA_NFD = chr(0x304B) + COMBINING_VOICED_SOUND_MARK
GI_NFD = chr(0x304D) + COMBINING_VOICED_SOUND_MARK

// 要入力確認の判定(DS 4.8): 前後の空白を除いた識別子の完全一致(大文字小文字を区別)でだけ実行ボタンを有効にする。
export function matchesIdentifier(input: string, expected: string): boolean {
  // 識別子が空なら、何を入力しても(空白だけでも)一致にしない(確認の意味がなくなる)。
  if (expected === '') return false
  return input.trim() === expected
}

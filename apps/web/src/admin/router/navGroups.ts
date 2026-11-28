// ナビグループの定義表(DS 5.3)。グループの順序と表示名だけを持ち、ナビ項目は route `meta.nav` が持つ。
// MVP はグループの見出し文字を出さない(区切り線だけ)ので、表示名は読み上げ用の `aria-label` と、将来の見出しに使う。
// 新しいグループが要るときだけ(例: AF-24 の `settings`)、ここに 1 行足す。
export const navGroups = [
  { id: 'overview', label: '全体' },
  { id: 'operate', label: '運用' },
  { id: 'inspect', label: '確認' },
] as const

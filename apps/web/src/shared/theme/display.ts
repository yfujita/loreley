// `useDisplay` の `mobile` の判定(DS 3.1・7)。
// 既定は `lg`(1145px)で、そのままだと 840〜1144px でも `mobile` と判定され、サイドバーが一時表示になり、
// 表がカード積みになる。ユーザー指示の「サイドバーは 840px 以上で常時表示」(R-1)に合わせて `md`(840px)にする。
export const displayOptions = { mobileBreakpoint: 'md' } as const

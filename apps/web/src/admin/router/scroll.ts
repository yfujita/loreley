// `scrollBehavior`(E 4.5): 画面が変わるときは先頭へ。クエリだけの変化(ページ・タブ・並べ替え)では動かさない。
// 戻る・進む(`savedPosition` がある)ときは、ブラウザが覚えている位置へ戻す。X1 のタブ移動の「表の上端まで」は画面側で行う。
import type { RouterScrollBehavior } from 'vue-router'

import { isSamePage } from './samePage'

export const scrollBehavior: RouterScrollBehavior = (to, from, savedPosition) => {
  if (savedPosition !== null) return savedPosition
  if (isSamePage(to, from)) return false
  return { top: 0 }
}

// ページングの定数(E 5.6)。J1(EP-09)・X1(EP-11)が共有する。
// API の `items_per_page` の列挙(25・50・100。既定 25)と、画面の `size`(URL)・`itemsPerPage`(Vuetify)の値。

export const ITEMS_PER_PAGE_OPTIONS = [25, 50, 100] as const
export type ItemsPerPage = (typeof ITEMS_PER_PAGE_OPTIONS)[number]
export const DEFAULT_ITEMS_PER_PAGE: ItemsPerPage = 25

export function isItemsPerPage(value: unknown): value is ItemsPerPage {
  return ITEMS_PER_PAGE_OPTIONS.some((option) => option === value)
}

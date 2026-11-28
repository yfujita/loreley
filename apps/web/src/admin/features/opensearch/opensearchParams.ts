// O1 の条件(URL のクエリ)の定義(E 5.6・opensearch 3.5)。`useListParams` に渡す。
// `q`(インデックス名)・`state`(green・yellow・red のカンマ区切り。例 `?q=logs&state=yellow,green`)。
// 条件の変更は `replace`(履歴を増やさない。J1・X1 の `push` との違い)。マトリクスのページ位置(`page`)は URL に入れない
// (1 ページの列数が幅で決まり、同じ URL でも幅によって意味が変わるため)。
// この定義は API には送らない(絞り込みは画面側。EP-12 にクエリはない)。
import type { LocationQuery } from 'vue-router'

import type { ListParamsDefinition } from '@/admin/composables/useListParams'
import { toClusterStatus } from '@/admin/lib/clusterValues'

import { canonicalStates, type RawIndexFilter } from './models/indexFilter'

function firstString(value: LocationQuery[string]): string {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' ? first : ''
}

export const opensearchParams: ListParamsDefinition<RawIndexFilter> = {
  parse: (query) => ({
    q: firstString(query.q).trim(),
    // 未知の値は無視する。
    states: canonicalStates(
      firstString(query.state)
        .split(',')
        .map((value) => toClusterStatus(value.trim()))
        .filter((status) => status !== null),
    ),
  }),
  serialize: (params) => ({
    ...(params.q !== '' && { q: params.q }),
    ...(params.states.length > 0 && { state: canonicalStates(params.states).join(',') }),
  }),
  navigation: 'replace',
}

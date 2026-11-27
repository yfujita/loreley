// 一覧の条件(URL のクエリ)と画面の状態の変換(E 5.6・F 3.5。FMOD-P-13)。
//
// URL が唯一の正(E 8章)。route の `query` から正規化した `params`(型付き)を作り、key・API 呼び出し・
// `VDataTableServer` の表示はすべて `params` から導く。ローカルに複製しない。
// 画面ごとの条件の定義(URL のキー・API のキー・既定値・正規化)は `features/*/*Params.ts` が持ち、ここに渡す。
import { computed, watch, type ComputedRef } from 'vue'
import { useRoute, useRouter, type LocationQuery } from 'vue-router'

export type ListParamsDefinition<TParams extends object> = {
  /** route の query から条件を作る。不正値(範囲外の `page`、未知の `sort`・`tab`・`size`)は既定値にする(正規化) */
  parse: (query: LocationQuery) => TParams
  /** 条件を URL のクエリにする。既定値は省略する */
  serialize: (params: TParams) => Record<string, string>
  /**
   * 条件の変更を履歴に積むか。ページ・件数・並べ替え・絞り込み・タブの変更は `push`(戻る・再読み込み・共有で再現)、
   * O1 の `q`・`state` は `replace`(opensearch 3.5)。正規化は常に `replace`。
   */
  navigation: 'push' | 'replace'
  /** ページ番号を持つキー。持たない画面(O1)は省略する */
  pageKey?: keyof TParams
  /** 変更したら 1 ページ目に戻るキー(絞り込み・件数・タブ・データソース)。ページと並べ替えは含めない */
  resetPageOn?: readonly (keyof TParams)[]
}

/** query の値が文字列 1 つのキーだけを取り出して比べる(配列・null は不一致)。 */
function toComparableQuery(
  query: LocationQuery | Record<string, string>,
): Record<string, string> | null {
  const result: Record<string, string> = {}
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined) continue
    if (typeof value !== 'string') return null
    result[key] = value
  }
  return result
}

function isSameQuery(current: LocationQuery, normalized: Record<string, string>): boolean {
  const left = toComparableQuery(current)
  const right = toComparableQuery(normalized)
  if (left === null || right === null) return false
  const leftKeys = Object.keys(left)
  return (
    leftKeys.length === Object.keys(right).length &&
    leftKeys.every((key) => left[key] === right[key])
  )
}

export function useListParams<TParams extends object>(
  definition: ListParamsDefinition<TParams>,
): {
  params: ComputedRef<TParams>
  /** 条件を変える。`resetPageOn` のキーを変えたときは、1 ページ目に戻す(`page` を指定していなければ) */
  update: (patch: Partial<TParams>) => Promise<void>
} {
  const route = useRoute()
  const router = useRouter()
  // この条件を持つ画面の route。別の画面へ遷移する途中で、この画面の条件を新しい URL に書き戻さないため。
  const ownerRouteName = route.name

  const params = computed(() => definition.parse(route.query))

  // 不正値は既定値にして `replace`(正規化)。初回表示と、URL の直接変更・戻る・進むの両方で行う。
  watch(
    () => route.fullPath,
    () => {
      if (route.name !== ownerRouteName) return
      const normalized = definition.serialize(params.value)
      if (isSameQuery(route.query, normalized)) return
      void router.replace({ query: normalized })
    },
    { immediate: true },
  )

  async function update(patch: Partial<TParams>): Promise<void> {
    const current = params.value
    const next = { ...current, ...patch }

    const { pageKey, resetPageOn = [] } = definition
    const changesFilter = resetPageOn.some(
      (key) => key in patch && JSON.stringify(patch[key]) !== JSON.stringify(current[key]),
    )
    if (pageKey !== undefined && changesFilter && !(pageKey in patch)) {
      // 1 ページ目に戻す。既定値の指定は `serialize` が省略する。
      const defaults = definition.parse({})
      next[pageKey] = defaults[pageKey]
    }

    const query = definition.serialize(next)
    if (isSameQuery(route.query, query)) return
    await (definition.navigation === 'push' ? router.push({ query }) : router.replace({ query }))
  }

  return { params, update }
}

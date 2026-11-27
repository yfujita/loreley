// @vitest-environment node
// 依存ルール(F 6 章 R1〜R17・1.2 のモジュール表・2.2 の層)を「ゾーン × モジュール」の行列で検査する。
//
// 期待値は、設計から**手で書いた許可リスト**で、eslint.config.js とは独立の情報源にしている
// (config を緩める・絞る変更は、ここの期待値との食い違いとして落ちる)。リストにないモジュールは、すべて禁止。
// 各セル: 値の import と型の import(`import type`)の両方を試す。
//   許可(A): どちらも通る / 禁止(D): どちらも落ちる / 型のみ(T): 値は落ち、型は通る / 不問(-): 設計に規定がなく検査しない
// 構文・グローバルの規則(R3 の fetch・R12〜R14 など)と例外の個別サンプルは dependencyRules.test.ts が持つ。
import { join } from 'node:path'

import { beforeAll, describe, expect, it, vi } from 'vitest'

import { eslint, WEB_DIR } from './eslintInstance'

vi.setConfig({ testTimeout: 60_000, hookTimeout: 60_000 })

/** 層ごとの代表的な import 先。 */
const MODULES = {
  sharedTheme: '@/shared/theme/tokens',
  sharedUi: '@/shared/ui/StatusTag',
  sharedApi: '@/shared/api/apiError',
  sharedLib: '@/shared/lib/datetime',
  api: '@/admin/api', // 公開口
  apiDeep: '@/admin/api/errors/toApiError', // 公開口以外の深い import(R2・E 11.1)
  lib: '@/admin/lib/viewState',
  queries: '@/admin/queries/jobs',
  queriesMeta: '@/admin/queries/meta',
  queriesMutations: '@/admin/queries/mutations/cancelJob',
  composables: '@/admin/composables/useListParams',
  components: '@/admin/components/data-table/AdminDataTable',
  templates: '@/admin/templates/ListPage',
  dialogs: '@/admin/dialogs/job-cancel/JobCancelDialog',
  shell: '@/admin/shell/AppShell',
  featureJobs: '@/admin/features/jobs/jobActions',
  featureSources: '@/admin/features/sources/sourceActions',
  router: '@/admin/router/routes',
  app: '@/admin/app/setupRouter',
  vue: 'vue',
  vueRouter: 'vue-router',
  vueQuery: '@tanstack/vue-query',
  vuetify: 'vuetify/components',
} as const
type ModuleKey = keyof typeof MODULES

type Cell = 'A' | 'D' | 'T' | '-'

type Row = {
  /** 行の見出し。設計の根拠(章・R 番号)を添える */
  zone: string
  path: string
  /** 値も型も import できるモジュール */
  allow: ModuleKey[]
  /** 型(import type)だけ import できるモジュール */
  typeOnly?: ModuleKey[]
  /** 設計に規定がなく、検査しないモジュール */
  unspecified?: ModuleKey[]
}

const SHARED = ['sharedTheme', 'sharedUi', 'sharedApi', 'sharedLib'] as const
const QUERIES = ['queries', 'queriesMeta', 'queriesMutations'] as const
const FEATURES = ['featureJobs', 'featureSources'] as const

const ROWS: Row[] = [
  // ── 層 0: shared(R1: admin/・vue-router・vue-query・生成コードを import しない。R13: vuetify の部品は .vue だけ)
  // shared 内の相互 import は R1 に規定がない(F 2.2 は同じ層の import を原則禁止)。実需のある範囲(ui→theme の icons・
  // lib の datetime、api→lib)だけを許可している。
  {
    zone: 'shared/theme(R1。R13: 部品を使ってよい)',
    path: 'src/shared/theme/tokens.ts',
    allow: [...SHARED, 'vue', 'vuetify'],
  },
  {
    zone: 'shared/ui の .ts(R1。R13: .vue 以外は型だけ)',
    path: 'src/shared/ui/statusMaps.ts',
    allow: [...SHARED, 'vue'],
    typeOnly: ['vuetify'],
  },
  {
    zone: 'shared/ui の .vue(R1。R13)',
    path: 'src/shared/ui/StatusTag.vue',
    allow: [...SHARED, 'vue', 'vuetify'],
  },
  {
    zone: 'shared/api(R1。生成型・fetch に依存しない純粋な定義。3.2)',
    path: 'src/shared/api/apiError.ts',
    allow: ['sharedApi', 'sharedLib', 'vue'],
  },
  {
    zone: 'shared/lib(R1。純粋。3.2)',
    path: 'src/shared/lib/datetime.ts',
    allow: ['sharedLib', 'vue'],
  },

  // ── 層 1: admin/api(R17: shared/api と自分の generated だけ。R4: vue-query 不可。R13: vuetify 不可)
  {
    zone: 'admin/api(R17)',
    path: 'src/admin/api/errors/toApiError.ts',
    allow: ['api', 'apiDeep', 'sharedApi'],
    unspecified: ['vue', 'vueRouter'],
  },
  // admin/lib(R5: 純粋。型は公開口 @/admin/api から可。vue は import type だけ)
  {
    zone: 'admin/lib(R5)',
    path: 'src/admin/lib/viewState.ts',
    allow: ['lib', ...SHARED],
    typeOnly: ['api', 'vue'],
  },

  // ── 層 2: admin/queries(R6: vue-router・.vue・vuetify・components 以上を import しない。1.2: 入力は admin/api。
  // composables は同じ層(F 2.2)、shared/ui・shared/theme は UI(R6「UI を知らない」)なので不可)
  {
    zone: 'admin/queries(R6)',
    path: 'src/admin/queries/jobs.ts',
    allow: [...QUERIES, 'api', 'lib', 'sharedApi', 'sharedLib', 'vue', 'vueQuery'],
  },
  // admin/composables(R16: queries・components・templates・dialogs・shell・features・router・app 不可。
  // vue・vue-router・@/admin/api(値も)・lib は可。R4: vue-query は useViewState.ts の型だけ)
  {
    zone: 'admin/composables(R16)',
    path: 'src/admin/composables/useListParams.ts',
    allow: ['composables', 'api', 'lib', ...SHARED, 'vue', 'vueRouter'],
  },
  {
    zone: 'admin/composables/useViewState.ts(R16・R4)',
    path: 'src/admin/composables/useViewState.ts',
    allow: ['composables', 'api', 'lib', ...SHARED, 'vue', 'vueRouter'],
    typeOnly: ['vueQuery'],
  },

  // ── 層 3: components・templates(R7: queries・admin/api の値・vue-router・features・dialogs・shell 不可。
  // composables・lib・shared は可。components と templates は同じ層(F 2.2・6 章)なので互いに不可)
  {
    zone: 'admin/components の .ts(R7。R13: 型だけ)',
    path: 'src/admin/components/data-table/columns.ts',
    allow: ['components', 'composables', 'lib', ...SHARED, 'vue'],
    typeOnly: ['api', 'vuetify'],
  },
  {
    zone: 'admin/components の .vue(R7。R13)',
    path: 'src/admin/components/data-table/AdminDataTable.vue',
    allow: ['components', 'composables', 'lib', ...SHARED, 'vue', 'vuetify'],
    typeOnly: ['api'],
  },
  {
    zone: 'admin/templates の .ts(R7。R13: 型だけ)',
    path: 'src/admin/templates/sample.ts',
    allow: ['templates', 'composables', 'lib', ...SHARED, 'vue'],
    typeOnly: ['api', 'vuetify'],
  },
  {
    zone: 'admin/templates の .vue(R7。R13)',
    path: 'src/admin/templates/ListPage.vue',
    allow: ['templates', 'composables', 'lib', ...SHARED, 'vue', 'vuetify'],
    typeOnly: ['api'],
  },

  // ── 層 4: dialogs(R9: features・shell・router・app 不可。queries/mutations と @/admin/api は可。
  // 1.2 の入力は queries(書き込み)・components。composables・lib・shared は R9 が禁止せず、層の向きでも可。
  // templates は 1.2 の入力になく不使用)
  {
    zone: 'admin/dialogs の .ts(R9。R13: 型だけ)',
    path: 'src/admin/dialogs/useOperationDialog.ts',
    allow: [
      'dialogs',
      'api',
      'components',
      'composables',
      'lib',
      ...SHARED,
      'queriesMutations',
      'vue',
    ],
    typeOnly: ['vuetify'],
    unspecified: ['vueRouter'],
  },
  {
    zone: 'admin/dialogs の .vue(R9。R13)',
    path: 'src/admin/dialogs/job-cancel/JobCancelDialog.vue',
    allow: [
      'dialogs',
      'api',
      'components',
      'composables',
      'lib',
      ...SHARED,
      'queriesMutations',
      'vue',
      'vuetify',
    ],
    unspecified: ['vueRouter'],
  },
  // shell(R10: features・dialogs・app 不可。queries/meta・composables・vue-router は可。
  // 1.2 の入力は composables・queries/meta・vue-router。@/admin/api は型だけ(層の向きで許され、R10 が禁止しない))
  {
    zone: 'admin/shell の .ts(R10。R13: 型だけ)',
    path: 'src/admin/shell/externalLinks.ts',
    allow: ['shell', 'composables', 'lib', ...SHARED, 'queriesMeta', 'vue', 'vueRouter'],
    typeOnly: ['api', 'vuetify'],
  },
  {
    zone: 'admin/shell の .vue(R10。R13)',
    path: 'src/admin/shell/AppShell.vue',
    allow: ['shell', 'composables', 'lib', ...SHARED, 'queriesMeta', 'vue', 'vueRouter', 'vuetify'],
    typeOnly: ['api'],
  },

  // ── 層 5: features/<A>(R8: 他の features・router・app 不可。1.2 の入力は queries・dialogs・components・templates・lib。
  // composables は useListParams など(3.4)で使う。shell は入力になく不使用)
  {
    zone: 'admin/features/jobs の .ts(R8。R13: 型だけ)',
    path: 'src/admin/features/jobs/jobActions.ts',
    allow: [
      'featureJobs',
      ...QUERIES,
      'api',
      'components',
      'templates',
      'dialogs',
      'composables',
      'lib',
      ...SHARED,
      'vue',
    ],
    typeOnly: ['vuetify'],
    unspecified: ['vueRouter'],
  },
  {
    zone: 'admin/features/jobs の .vue(R8。R13)',
    path: 'src/admin/features/jobs/pages/JobsListPage.vue',
    allow: [
      'featureJobs',
      ...QUERIES,
      'api',
      'components',
      'templates',
      'dialogs',
      'composables',
      'lib',
      ...SHARED,
      'vue',
      'vuetify',
    ],
    unspecified: ['vueRouter'],
  },

  // ── 層 6: router(R11: features のページ・templates(404)・lib を import。queries・shell・app 不可。
  // composables は R11 が禁止せず、ガードのタイトル更新などで使う(FMOD-U-10)。R13 の列挙に無いので vuetify 不可)
  {
    zone: 'admin/router の .ts(R11・R13)',
    path: 'src/admin/router/routes.ts',
    allow: [
      'router',
      'templates',
      'composables',
      'lib',
      ...FEATURES,
      ...SHARED,
      'vue',
      'vueRouter',
    ],
  },
  {
    zone: 'admin/router の .vue(R11・R13)',
    path: 'src/admin/router/NotFoundPage.vue',
    allow: [
      'router',
      'templates',
      'composables',
      'lib',
      ...FEATURES,
      ...SHARED,
      'vue',
      'vueRouter',
    ],
  },

  // ── 層 7: app(下の層をすべて import してよい。R4: vue-query は setupQuery.ts だけ。
  // R13: vuetify・createVuetify は setupVuetify.ts だけ。公開口以外の admin/api の深い import は不可。R2)
  {
    zone: 'admin/app/setupRouter.ts(R4・R13)',
    path: 'src/admin/app/setupRouter.ts',
    allow: [
      'api',
      'lib',
      ...QUERIES,
      'composables',
      'components',
      'templates',
      'dialogs',
      'shell',
      ...FEATURES,
      'router',
      'app',
      ...SHARED,
      'vue',
    ],
    unspecified: ['vueRouter'],
  },
  {
    zone: 'admin/app/App.vue(R4・R13)',
    path: 'src/admin/app/App.vue',
    allow: [
      'api',
      'lib',
      ...QUERIES,
      'composables',
      'components',
      'templates',
      'dialogs',
      'shell',
      ...FEATURES,
      'router',
      'app',
      ...SHARED,
      'vue',
    ],
    unspecified: ['vueRouter'],
  },
  {
    zone: 'admin/app/setupQuery.ts(R4: vue-query 可)',
    path: 'src/admin/app/setupQuery.ts',
    allow: [
      'api',
      'lib',
      ...QUERIES,
      'composables',
      'components',
      'templates',
      'dialogs',
      'shell',
      ...FEATURES,
      'router',
      'app',
      ...SHARED,
      'vue',
      'vueQuery',
    ],
    unspecified: ['vueRouter'],
  },
  {
    zone: 'admin/app/setupVuetify.ts(R13: vuetify 可)',
    path: 'src/admin/app/setupVuetify.ts',
    allow: [
      'api',
      'lib',
      ...QUERIES,
      'composables',
      'components',
      'templates',
      'dialogs',
      'shell',
      ...FEATURES,
      'router',
      'app',
      ...SHARED,
      'vue',
      'vuetify',
    ],
    unspecified: ['vueRouter'],
  },

  // ── main.ts(2.4・R15: admin/app と公開口 @/admin/api(configureApiClient)・vuetify/styles だけ)
  {
    zone: 'main.ts(2.4・R15)',
    path: 'src/main.ts',
    allow: ['app', 'api', ...SHARED, 'vue'],
    unspecified: ['vueRouter'],
  },

  // ── どのゾーンにも属さないファイル: 最も厳しい規則(`allow: []`)
  {
    zone: '未所属のファイル',
    path: 'src/admin/foo/sample.ts',
    allow: [],
    unspecified: ['vue', 'vueRouter', 'vueQuery', 'vuetify'],
  },
]

function expectedCell(row: Row, key: ModuleKey): Cell {
  if (row.allow.includes(key)) return 'A'
  if (row.typeOnly?.includes(key)) return 'T'
  if (row.unspecified?.includes(key)) return '-'
  return 'D'
}

const MODULE_KEYS = Object.keys(MODULES) as ModuleKey[]

/** 全モジュールの import を 1 ファイルに並べて 1 回で検査し、import 文の行番号から結果を戻す。 */
async function lintImports(row: Row, kind: 'value' | 'type'): Promise<Map<ModuleKey, boolean>> {
  const importLines = MODULE_KEYS.map((key, index) =>
    kind === 'value'
      ? `import { x${index} } from '${MODULES[key]}'`
      : `import type { X${index} } from '${MODULES[key]}'`,
  )
  const exportLine =
    kind === 'value'
      ? `export { ${MODULE_KEYS.map((_, index) => `x${index}`).join(', ')} }`
      : `export type Y = [${MODULE_KEYS.map((_, index) => `X${index}`).join(', ')}]`
  const isVue = row.path.endsWith('.vue')
  const code = isVue
    ? `<script setup lang="ts">\n${importLines.join('\n')}\n${exportLine.replace(/^export /, '// ')}\n</script>\n<template><div /></template>\n`
    : `${importLines.join('\n')}\n${exportLine}\n`
  const firstImportLine = isVue ? 2 : 1

  const [result] = await eslint.lintText(code, { filePath: join(WEB_DIR, row.path) })
  const restrictedLines = new Set(
    (result?.messages ?? [])
      .filter((message) => message.ruleId === 'no-restricted-imports')
      .map((message) => message.line),
  )
  return new Map(
    MODULE_KEYS.map((key, index) => [key, restrictedLines.has(firstImportLine + index)]),
  )
}

describe('依存ルールの行列(ゾーン × モジュール)', () => {
  beforeAll(async () => {
    await lintImports(ROWS[0]!, 'value')
  })

  it.each(ROWS)('$zone($path)', async (row) => {
    const [valueRestricted, typeRestricted] = await Promise.all([
      lintImports(row, 'value'),
      lintImports(row, 'type'),
    ])

    const mismatches: string[] = []
    for (const key of MODULE_KEYS) {
      const expected = expectedCell(row, key)
      if (expected === '-') continue
      const value = valueRestricted.get(key)
      const type = typeRestricted.get(key)
      const actual = !value && !type ? 'A' : value && type ? 'D' : value && !type ? 'T' : '?'
      if (actual !== expected) {
        mismatches.push(
          `${MODULES[key]}: 期待 ${expected}(A 許可 / D 禁止 / T 型のみ)、実際 ${actual}`,
        )
      }
    }

    expect(mismatches).toEqual([])
  })
})

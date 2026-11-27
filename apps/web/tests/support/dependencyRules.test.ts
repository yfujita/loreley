// @vitest-environment node
// 依存ルール R1〜R17(F 6 章)と、それを表す eslint.config.js のゾーンの回帰テスト。
// `npm run lint` は実ファイルしか検査しないので、規則を変えたときに、違反が止まらなくなることをここで検出する。
// 各行は「ファイルの場所(ゾーンが決まる)・コード・期待する違反」。違反を期待しない行は、例外として許される書き方。
import { readdirSync } from 'node:fs'
import { join, relative } from 'node:path'

import { beforeAll, describe, expect, it, vi } from 'vitest'

import { eslint, WEB_DIR } from './eslintInstance'

// ESLint の初回の読み込み(config・パーサー)に数秒かかる。
vi.setConfig({ testTimeout: 60_000, hookTimeout: 60_000 })

type Violation = {
  rule: string
  ruleId: string
  /** メッセージに含まれる文字列(R 番号や理由) */
  message: string
}
type Sample = {
  /** 表の見出し(どの規則の、どういう書き方か) */
  title: string
  path: string
  code: string
  /** 期待する違反。省略すると「違反なし(許される書き方)」 */
  violation?: Violation
}

const IMPORT = 'no-restricted-imports'
const GLOBALS = 'no-restricted-globals'
const PROPERTIES = 'no-restricted-properties'
const SYNTAX = 'no-restricted-syntax'

const violates = (rule: string, ruleId: string, message = rule): Violation => ({
  rule,
  ruleId,
  message,
})

/** `import { x } from '<source>'` を使って export する、最小のモジュール。 */
const importing = (source: string) => `import { x } from '${source}'\nexport { x }\n`
const importingType = (source: string) => `import type { X } from '${source}'\nexport type Y = X\n`
const vueFile = (script: string) =>
  `<script setup lang="ts">\n${script}\n</script>\n<template><div /></template>\n`

const SAMPLES: Sample[] = [
  // ── R1: shared は admin/・vue-router・vue-query・生成コードを import しない
  {
    title: 'shared/ui が admin/lib を import',
    path: 'src/shared/ui/Sample.ts',
    code: importing('@/admin/lib/a'),
    violation: violates('R1', IMPORT, '依存ルール'),
  },
  {
    title: 'shared/ui が vue-router を import',
    path: 'src/shared/ui/Sample.ts',
    code: importing('vue-router'),
    violation: violates('R1', IMPORT, 'R1'),
  },
  {
    title: 'shared/lib が vue-query を import',
    path: 'src/shared/lib/sample.ts',
    code: importing('@tanstack/vue-query'),
    violation: violates('R1', IMPORT, 'R4'),
  },
  {
    title: 'shared/lib が生成コードを import',
    path: 'src/shared/lib/sample.ts',
    code: importing('@/admin/api/generated/client.gen'),
    violation: violates('R1', IMPORT, '依存ルール'),
  },

  // ── R2: 生成コードは admin/api の中だけ。外は公開口 @/admin/api から
  {
    title: 'components が生成コードを import',
    path: 'src/admin/components/x/sample.ts',
    code: importing('@/admin/api/generated/client.gen'),
    violation: violates('R2', IMPORT),
  },
  {
    title: 'queries が generated ディレクトリを import',
    path: 'src/admin/queries/sample.ts',
    code: importing('@/admin/api/generated'),
    violation: violates('R2', IMPORT),
  },
  {
    title: 'queries が公開口以外の深い import(errors)をする',
    path: 'src/admin/queries/sample.ts',
    code: importing('@/admin/api/errors/toApiError'),
    violation: violates('R2', IMPORT),
  },
  {
    title: 'テストが生成コードを @/ で import',
    path: 'tests/support/sample.ts',
    code: importing('@/admin/api/generated/client.gen'),
    violation: violates('R2', IMPORT),
  },
  {
    title: 'テストが生成コードを相対パスで import',
    path: 'tests/support/sample.ts',
    code: importing('../../src/admin/api/generated/client.gen'),
    violation: violates('R2', IMPORT, '相対パス'),
  },
  {
    title: 'テストが生成コードを動的 import',
    path: 'tests/support/sample.ts',
    code: `export const load = () => import('../../src/admin/api/generated/client.gen')\n`,
    violation: violates('R2', SYNTAX),
  },
  {
    title: 'テストが公開口の型だけを import(許される)',
    path: 'tests/support/sample.ts',
    code: importingType('@/admin/api'),
  },
  {
    title: 'admin/api の中での ./generated の import(許される)',
    path: 'src/admin/api/sample.ts',
    code: importing('./generated/client.gen'),
  },
  {
    title: 'admin/api の中での @/ 形式の generated の import(許される)',
    path: 'src/admin/api/sample.ts',
    code: importing('@/admin/api/generated'),
  },
  {
    title: 'テストの中の admin/api の ./generated の import(許される)',
    path: 'src/admin/api/errors/sample.contract.test.ts',
    code: importing('../generated/types.gen'),
  },
  {
    title: 'queries が公開口 @/admin/api を import(許される)',
    path: 'src/admin/queries/sample.ts',
    code: importing('@/admin/api'),
  },

  // ── R3: HTTP の入口は admin/api と shared/api
  {
    title: 'lib が fetch を呼ぶ',
    path: 'src/admin/lib/sample.ts',
    code: `export const response = fetch('/x')\n`,
    violation: violates('R3', GLOBALS),
  },
  {
    title: 'lib が XMLHttpRequest を使う',
    path: 'src/admin/lib/sample.ts',
    code: `export const request = new XMLHttpRequest()\n`,
    violation: violates('R3', GLOBALS),
  },
  {
    title: 'lib が window.fetch を参照',
    path: 'src/admin/lib/sample.ts',
    code: `export const request = window.fetch\n`,
    violation: violates('R3', PROPERTIES),
  },
  {
    title: 'features の .vue が fetch を呼ぶ',
    path: 'src/admin/features/jobs/pages/SampleJobPage.vue',
    code: vueFile(`const response = fetch('/x')\nvoid response`),
    violation: violates('R3', GLOBALS),
  },
  {
    title: "lib が文字列 '/api/admin/v1' を持つ",
    path: 'src/admin/lib/sample.ts',
    code: `export const base = '/api/admin/v1/jobs'\n`,
    violation: violates('R3', SYNTAX),
  },
  {
    title: "lib がテンプレートリテラルに '/api/admin/v1' を持つ",
    path: 'src/admin/lib/sample.ts',
    code: 'export const url = `/api/admin/v1/${1}`\n',
    violation: violates('R3', SYNTAX),
  },
  {
    title: 'lib が @hey-api/* を import',
    path: 'src/admin/lib/sample.ts',
    code: importing('@hey-api/client-fetch'),
    violation: violates('R3', IMPORT),
  },
  {
    title: 'テストが @hey-api/* を import',
    path: 'src/admin/lib/sample.test.ts',
    code: importing('@hey-api/client-fetch'),
    violation: violates('R3', IMPORT),
  },
  {
    title: 'テストが fetch を呼ぶ',
    path: 'tests/support/sample.ts',
    code: `export const response = fetch('/x')\n`,
    violation: violates('R3', GLOBALS),
  },
  {
    title: 'admin/api が fetch と文字列 /api/admin/v1 を使う(許される)',
    path: 'src/admin/api/sample.ts',
    code: `export const response = fetch('/api/admin/v1')\n`,
  },
  {
    title: 'shared/api が fetch と文字列 /api/admin/v1 を使う(許される)',
    path: 'src/shared/api/sample.ts',
    code: `export const response = fetch('/api/admin/v1')\n`,
  },
  {
    title: 'テストが fetch を差し替え、モックのパスを書く(許される)',
    path: 'tests/support/sample.ts',
    code: `globalThis.fetch = (() => Promise.resolve(new Response())) as typeof fetch\nexport const pattern = '**/api/admin/v1/**'\n`,
  },

  // ── R4: vue-query は queries と setupQuery.ts だけ(型は useViewState.ts でも可)
  {
    title: 'features が vue-query を import',
    path: 'src/admin/features/jobs/sample.ts',
    code: importing('@tanstack/vue-query'),
    violation: violates('R4', IMPORT),
  },
  {
    title: 'composables(useViewState.ts 以外)が vue-query の型を import',
    path: 'src/admin/composables/sample.ts',
    code: importingType('@tanstack/vue-query'),
    violation: violates('R4', IMPORT),
  },
  {
    title: 'admin/api が vue-query を import',
    path: 'src/admin/api/sample.ts',
    code: importing('@tanstack/vue-query'),
    violation: violates('R4', IMPORT),
  },
  {
    title: 'useViewState.ts が vue-query の型を import(許される)',
    path: 'src/admin/composables/useViewState.ts',
    code: importingType('@tanstack/vue-query'),
  },
  {
    title: 'useViewState.ts が vue-query の値を import',
    path: 'src/admin/composables/useViewState.ts',
    code: importing('@tanstack/vue-query'),
    violation: violates('R4', IMPORT),
  },
  {
    title: 'queries が vue-query を import(許される)',
    path: 'src/admin/queries/sample.ts',
    code: importing('@tanstack/vue-query'),
  },
  {
    title: 'app/setupQuery.ts が vue-query を import(許される)',
    path: 'src/admin/app/setupQuery.ts',
    code: importing('@tanstack/vue-query'),
  },
  {
    title: 'app/setupRouter.ts が vue-query を import',
    path: 'src/admin/app/setupRouter.ts',
    code: importing('@tanstack/vue-query'),
    violation: violates('R4', IMPORT),
  },

  // ── R5: lib は純粋(型は @/admin/api から可。vue は import type だけ)
  {
    title: 'lib が vue の値を import',
    path: 'src/admin/lib/sample.ts',
    code: importing('vue'),
    violation: violates('R5', IMPORT),
  },
  {
    title: 'lib が vue の型(InjectionKey)を import(許される)',
    path: 'src/admin/lib/sample.ts',
    code: importingType('vue'),
  },
  {
    title: 'lib が vue-router を import',
    path: 'src/admin/lib/sample.ts',
    code: importing('vue-router'),
    violation: violates('R5', IMPORT),
  },
  {
    title: 'lib が vuetify を import',
    path: 'src/admin/lib/sample.ts',
    code: importing('vuetify/components'),
    violation: violates('R5', IMPORT, 'R13'),
  },
  {
    title: 'lib が .vue を import',
    path: 'src/admin/lib/sample.ts',
    code: importing('@/shared/ui/StatusTag.vue'),
    violation: violates('R5', IMPORT),
  },
  {
    title: 'lib が queries を import',
    path: 'src/admin/lib/sample.ts',
    code: importing('@/admin/queries/jobs'),
    violation: violates('R5', IMPORT),
  },
  {
    title: 'lib が公開口の値を import',
    path: 'src/admin/lib/sample.ts',
    code: importing('@/admin/api'),
    violation: violates('R5', IMPORT),
  },
  {
    title: 'lib が公開口の型を import(許される)',
    path: 'src/admin/lib/sample.ts',
    code: importingType('@/admin/api'),
  },

  // ── R6: queries は UI を知らない
  {
    title: 'queries が vue-router を import',
    path: 'src/admin/queries/sample.ts',
    code: importing('vue-router'),
    violation: violates('R6', IMPORT),
  },
  {
    title: 'queries が components を import',
    path: 'src/admin/queries/sample.ts',
    code: importing('@/admin/components/a'),
    violation: violates('R6', IMPORT),
  },
  {
    title: 'queries が vuetify を import',
    path: 'src/admin/queries/sample.ts',
    code: importing('vuetify/components'),
    violation: violates('R6', IMPORT, 'R13'),
  },
  {
    title: 'queries が features を import',
    path: 'src/admin/queries/sample.ts',
    code: importing('@/admin/features/jobs/a'),
    violation: violates('R6', IMPORT),
  },

  // ── R7: components・templates はデータ取得を知らない
  {
    title: 'components が queries を import',
    path: 'src/admin/components/sample.ts',
    code: importing('@/admin/queries/jobs'),
    violation: violates('R7', IMPORT),
  },
  {
    title: 'components が公開口の値を import',
    path: 'src/admin/components/sample.ts',
    code: importing('@/admin/api'),
    violation: violates('R7', IMPORT),
  },
  {
    title: 'components が公開口の型を import(許される)',
    path: 'src/admin/components/sample.ts',
    code: importingType('@/admin/api'),
  },
  {
    title: 'templates が vue-router を import',
    path: 'src/admin/templates/sample.ts',
    code: importing('vue-router'),
    violation: violates('R7', IMPORT),
  },
  {
    title: 'templates が shell を import',
    path: 'src/admin/templates/sample.ts',
    code: importing('@/admin/shell/a'),
    violation: violates('R7', IMPORT),
  },
  {
    title: 'templates が components(同じ層)を import',
    path: 'src/admin/templates/sample.ts',
    code: importing('@/admin/components/a'),
    violation: violates('R7', IMPORT),
  },
  {
    title: 'components が型だけ vuetify から import(許される)',
    path: 'src/admin/components/sample.ts',
    code: importingType('vuetify/components'),
  },

  // ── R8: features どうし・router・app を import しない
  {
    title: 'features が他の feature を import',
    path: 'src/admin/features/jobs/sample.ts',
    code: importing('@/admin/features/sources/a'),
    violation: violates('R8', IMPORT),
  },
  {
    title: 'features が router を import',
    path: 'src/admin/features/jobs/sample.ts',
    code: importing('@/admin/router'),
    violation: violates('R8', IMPORT),
  },
  {
    title: 'features が shell を import(設計 1.2 の入力に無い)',
    path: 'src/admin/features/jobs/sample.ts',
    code: importing('@/admin/shell/a'),
    violation: violates('R8', IMPORT, '依存ルール'),
  },
  {
    title:
      'features が queries・dialogs・templates・components・自分の feature を import(許される)',
    path: 'src/admin/features/jobs/sample.ts',
    code: [
      `import { a } from '@/admin/queries/jobs'`,
      `import { b } from '@/admin/dialogs/job-cancel/a'`,
      `import { c } from '@/admin/templates/a'`,
      `import { d } from '@/admin/components/a'`,
      `import { e } from '@/admin/features/jobs/b'`,
      `export { a, b, c, d, e }`,
      '',
    ].join('\n'),
  },

  // ── R9: dialogs は features・shell・router・app を import しない。queries は mutations だけ
  {
    title: 'dialogs が features を import',
    path: 'src/admin/dialogs/sample.ts',
    code: importing('@/admin/features/jobs/a'),
    violation: violates('R9', IMPORT),
  },
  {
    title: 'dialogs が queries の読み取りを import',
    path: 'src/admin/dialogs/sample.ts',
    code: importing('@/admin/queries/jobs'),
    violation: violates('R9', IMPORT),
  },
  {
    title: 'dialogs が queries/mutations を import(許される)',
    path: 'src/admin/dialogs/sample.ts',
    code: importing('@/admin/queries/mutations/a'),
  },

  // ── R10: shell は features・dialogs・app を import しない。queries は meta だけ
  {
    title: 'shell が dialogs を import',
    path: 'src/admin/shell/sample.ts',
    code: importing('@/admin/dialogs/a'),
    violation: violates('R10', IMPORT),
  },
  {
    title: 'shell が queries の meta 以外を import',
    path: 'src/admin/shell/sample.ts',
    code: importing('@/admin/queries/jobs'),
    violation: violates('R10', IMPORT),
  },
  {
    title: 'shell が queries/meta・composables・vue-router を import(許される)',
    path: 'src/admin/shell/sample.ts',
    code: [
      `import { a } from '@/admin/queries/meta'`,
      `import { b } from '@/admin/composables/useBreadcrumbs'`,
      `import { c } from 'vue-router'`,
      `export { a, b, c }`,
      '',
    ].join('\n'),
  },

  // ── R11: router は features のページ・templates・lib だけ。queries・shell・app は import しない
  {
    title: 'router が queries を import',
    path: 'src/admin/router/sample.ts',
    code: importing('@/admin/queries/meta'),
    violation: violates('R11', IMPORT),
  },
  {
    title: 'router が shell を import',
    path: 'src/admin/router/sample.ts',
    code: importing('@/admin/shell/a'),
    violation: violates('R11', IMPORT),
  },
  {
    title: 'router が components を import(設計 R11 の入力に無い)',
    path: 'src/admin/router/sample.ts',
    code: importing('@/admin/components/a'),
    violation: violates('R11', IMPORT),
  },
  {
    title: 'router が features のページ・templates・lib を import(許される)',
    path: 'src/admin/router/sample.ts',
    code: [
      `import { a } from '@/admin/features/jobs/pages/JobsListPage.vue'`,
      `import { b } from '@/admin/templates/ListPage.vue'`,
      `import { c } from '@/admin/lib/routeNames'`,
      `export { a, b, c }`,
      '',
    ].join('\n'),
  },

  // ── R12: @mdi/js は shared/theme/icons.ts だけ。@mdi/font は禁止
  {
    title: 'icons.ts 以外が @mdi/js を import',
    path: 'src/shared/theme/sample.ts',
    code: importing('@mdi/js'),
    violation: violates('R12', IMPORT),
  },
  {
    title: '@mdi/font を import',
    path: 'src/admin/lib/sample.ts',
    code: `import '@mdi/font/css/materialdesignicons.css'\n`,
    violation: violates('R12', IMPORT),
  },
  {
    title: 'icons.ts が @mdi/js を import(許される)',
    path: 'src/shared/theme/icons.ts',
    code: importing('@mdi/js'),
  },

  // ── R13: vuetify の部品は .vue だけ。createVuetify は setupVuetify.ts だけ
  {
    title: 'admin/api が vuetify を import',
    path: 'src/admin/api/sample.ts',
    code: importing('vuetify/components'),
    violation: violates('R13', IMPORT),
  },
  {
    title: 'composables が vuetify を import',
    path: 'src/admin/composables/sample.ts',
    code: importing('vuetify'),
    violation: violates('R13', IMPORT),
  },
  {
    title: 'components の .ts が vuetify の値を import',
    path: 'src/admin/components/sample.ts',
    code: importing('vuetify/components'),
    violation: violates('R13', IMPORT),
  },
  {
    title: 'router が vuetify を import(.vue も不可。R13 の列挙に無い)',
    path: 'src/admin/router/SampleRoutePage.vue',
    code: vueFile(`import { VBtn } from 'vuetify/components'\nvoid VBtn`),
    violation: violates('R13', IMPORT),
  },
  {
    title: 'app の .vue が vuetify を import(R13 の列挙に無い)',
    path: 'src/admin/app/SampleApp.vue',
    code: vueFile(`import { VBtn } from 'vuetify/components'\nvoid VBtn`),
    violation: violates('R13', IMPORT),
  },
  {
    title: 'features の .vue が createVuetify を import',
    path: 'src/admin/features/jobs/pages/SampleJobPage.vue',
    code: vueFile(`import { createVuetify } from 'vuetify'\nvoid createVuetify`),
    violation: violates('R13', IMPORT),
  },
  {
    title: 'app の setupVuetify.ts 以外が createVuetify を import',
    path: 'src/admin/app/sample.ts',
    code: importing('vuetify'),
    violation: violates('R13', IMPORT),
  },
  {
    title: 'features の .vue が vuetify/styles を import',
    path: 'src/admin/features/jobs/pages/SampleJobPage.vue',
    code: vueFile(`import 'vuetify/styles'`),
    violation: violates('R13', IMPORT),
  },
  {
    title: 'features の .vue が vuetify の部品を import(許される)',
    path: 'src/admin/features/jobs/pages/SampleJobPage.vue',
    code: vueFile(`import { VBtn } from 'vuetify/components'\nvoid VBtn`),
  },
  {
    title: 'setupVuetify.ts が createVuetify を import(許される)',
    path: 'src/admin/app/setupVuetify.ts',
    code: importing('vuetify'),
  },
  {
    title: 'main.ts が vuetify/styles を import(許される)',
    path: 'src/main.ts',
    code: `import 'vuetify/styles'\n`,
  },
  {
    title: 'main.ts が vuetify の部品を import',
    path: 'src/main.ts',
    code: importing('vuetify/components'),
    violation: violates('R13', IMPORT),
  },

  // ── R14: localStorage・sessionStorage を使わない
  {
    title: 'localStorage を使う',
    path: 'src/admin/lib/sample.ts',
    code: `export const value = localStorage.getItem('a')\n`,
    violation: violates('R14', GLOBALS),
  },
  {
    title: 'window.sessionStorage を使う',
    path: 'src/admin/lib/sample.ts',
    code: `export const value = window.sessionStorage\n`,
    violation: violates('R14', PROPERTIES),
  },

  // ── R15: admin/app を import するのは main.ts だけ
  {
    title: 'features が admin/app を import',
    path: 'src/admin/features/jobs/sample.ts',
    code: importing('@/admin/app/App.vue'),
    // メッセージの番号は、import する側のゾーン(features は R8)のもの。
    violation: violates('R15', IMPORT, 'import できない'),
  },
  {
    title: 'main.ts が admin/app を import(許される)',
    path: 'src/main.ts',
    code: importing('@/admin/app/App.vue'),
  },
  {
    title: 'main.ts が router を import(設計 2.4: main.ts は admin/app だけ)',
    path: 'src/main.ts',
    code: importing('@/admin/router'),
    violation: violates('R15', IMPORT),
  },

  // ── R16: composables は queries・components などを import しない
  {
    title: 'composables が queries を import',
    path: 'src/admin/composables/sample.ts',
    code: importing('@/admin/queries/jobs'),
    violation: violates('R16', IMPORT),
  },

  // ── R17: admin/api は admin/ 内の他モジュールを import しない
  {
    title: 'admin/api が lib を import',
    path: 'src/admin/api/sample.ts',
    code: importing('@/admin/lib/a'),
    violation: violates('R17', IMPORT),
  },
  {
    title: 'admin/api が shared/lib を import',
    path: 'src/admin/api/sample.ts',
    code: importing('@/shared/lib/a'),
    violation: violates('R17', IMPORT),
  },
  {
    title: 'admin/api が shared/api を import(許される)',
    path: 'src/admin/api/sample.ts',
    code: importing('@/shared/api/a'),
  },

  // ── 親ディレクトリへの相対 import(設計に無い追加規則。層をまたぐ回避を止める)
  {
    title: '../ の相対 import',
    path: 'src/admin/lib/sample.ts',
    code: importing('../queries/a'),
    violation: violates('相対 import', IMPORT, '親ディレクトリ'),
  },
  {
    title: './../ の相対 import',
    path: 'src/admin/lib/sample.ts',
    code: importing('./../queries/a'),
    violation: violates('相対 import', IMPORT, '親ディレクトリ'),
  },
  {
    title: '.. だけの相対 import',
    path: 'src/admin/lib/sample.ts',
    code: importing('..'),
    violation: violates('相対 import', IMPORT, '親ディレクトリ'),
  },
  {
    title: '同じディレクトリの ./ の相対 import(許される)',
    path: 'src/admin/lib/sample.ts',
    code: importing('./other'),
  },
  {
    title: 'テストは ../ の相対 import をしてよい(許される)',
    path: 'src/admin/lib/sample.test.ts',
    code: importing('../../../tests/support/fetchStub'),
  },

  // ── 動的 import・import.meta.glob(FMOD-P-17: すべて同期 import)
  {
    title: 'features が動的 import',
    path: 'src/admin/features/jobs/sample.ts',
    code: `export const load = () => import('./other')\n`,
    violation: violates('FMOD-P-17', SYNTAX, '動的 import'),
  },
  {
    title: 'router が動的 import(.vue のルート遅延読み込み)',
    path: 'src/admin/router/sample.ts',
    code: `export const load = () => import('@/admin/features/jobs/pages/JobsListPage.vue')\n`,
    violation: violates('FMOD-P-17', SYNTAX, '動的 import'),
  },
  {
    title: 'main.ts が動的 import',
    path: 'src/main.ts',
    code: `export const load = () => import('./other')\n`,
    violation: violates('FMOD-P-17', SYNTAX, '動的 import'),
  },
  {
    title: 'admin/api が動的 import',
    path: 'src/admin/api/sample.ts',
    code: `export const load = () => import('./other')\n`,
    violation: violates('FMOD-P-17', SYNTAX, '動的 import'),
  },
  {
    title: 'import.meta.glob',
    path: 'src/admin/features/jobs/sample.ts',
    code: `export const modules = import.meta.glob('./pages/*.vue')\n`,
    violation: violates('FMOD-P-17', SYNTAX, 'import.meta.glob'),
  },
  {
    title: 'import.meta.globEager',
    path: 'src/admin/lib/sample.ts',
    code: `export const modules = import.meta.globEager('./*.ts')\n`,
    violation: violates('FMOD-P-17', SYNTAX, 'import.meta.glob'),
  },
  {
    title: 'テストは動的 import をしてよい(許される)',
    path: 'tests/support/sample.ts',
    code: `export const load = () => import('./other')\n`,
  },

  // ── ゾーンに属さないファイル: 最も厳しい規則を掛け、ファイルがあること自体を違反にする
  {
    title: '未所属のディレクトリ(admin/foo)',
    path: 'src/admin/foo/sample.ts',
    code: `export const a = 1\n`,
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
  {
    title: '未所属のディレクトリ(shared/foo)',
    path: 'src/shared/foo/sample.ts',
    code: `export const a = 1\n`,
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
  {
    title: 'features 直下のファイル',
    path: 'src/admin/features/sample.ts',
    code: `export const a = 1\n`,
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
  {
    title: 'FEATURES に無い feature',
    path: 'src/admin/features/unknown/sample.ts',
    code: `export const a = 1\n`,
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
  {
    title: 'lib の .vue',
    path: 'src/admin/lib/Sample.vue',
    code: vueFile(`const a = 1\nvoid a`),
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
  {
    title: 'queries の .vue',
    path: 'src/admin/queries/Sample.vue',
    code: vueFile(`const a = 1\nvoid a`),
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
  {
    title: 'shared/api の .vue',
    path: 'src/shared/api/Sample.vue',
    code: vueFile(`const a = 1\nvoid a`),
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
  {
    title: '未所属のファイルでの import の違反も止める(最も厳しい規則)',
    path: 'src/admin/foo/sample.ts',
    code: importing('@/admin/lib/a'),
    violation: violates('未所属', IMPORT, '依存ルール'),
  },

  // ── import type の副作用(verbatimModuleSyntax)
  {
    title: 'import { type X } は副作用 import として残る',
    path: 'src/admin/lib/sample.ts',
    code: `import { type X } from 'vue'\nexport type Y = X\n`,
    violation: violates('型の import', '@typescript-eslint/no-import-type-side-effects', 'import'),
  },
  // ── src/ は Node の API(process・Buffer)を使わない(tsconfig.app.json は Node の型を持たない)
  {
    title: 'src の lib が process を使う',
    path: 'src/admin/lib/sample.ts',
    code: `export const mode = process.env.NODE_ENV\n`,
    violation: violates('Node API', GLOBALS, 'process'),
  },
  {
    title: 'src の features の .vue が Buffer を使う',
    path: 'src/admin/features/jobs/pages/SampleJobPage.vue',
    code: vueFile(`const bytes = Buffer.from('a')\nvoid bytes`),
    violation: violates('Node API', GLOBALS, 'Buffer'),
  },
  {
    title: 'main.ts が process を使う',
    path: 'src/main.ts',
    code: `export const mode = process.env.NODE_ENV\n`,
    violation: violates('Node API', GLOBALS, 'process'),
  },
  {
    title: 'テストは process を使ってよい(許される)',
    path: 'src/admin/lib/sample.test.ts',
    code: `export const dir = process.cwd()\n`,
  },
  {
    title: 'tests/ は process を使ってよい(許される)',
    path: 'tests/support/sample.ts',
    code: `export const dir = process.cwd()\n`,
  },
  {
    title: 'vite.config.ts など src 外の設定ファイルは process を使ってよい(許される)',
    path: 'vite.config.ts',
    code: `export const target = process.env.LORELEY_DEV_API_TARGET\n`,
  },

  // ── タイマーは window.setTimeout / window.setInterval で書く(戻り値の型を number にそろえる)
  {
    title: 'src の lib が素の setTimeout を使う',
    path: 'src/admin/lib/sample.ts',
    code: `export const timer = setTimeout(() => {}, 1)\n`,
    violation: violates('タイマー', GLOBALS, 'window.setTimeout'),
  },
  {
    title: 'src の composables が素の setInterval を使う',
    path: 'src/admin/composables/sample.ts',
    code: `export const timer = setInterval(() => {}, 1)\n`,
    violation: violates('タイマー', GLOBALS, 'window.setTimeout'),
  },
  {
    title: 'src の features の .vue が素の setTimeout を使う',
    path: 'src/admin/features/jobs/pages/SampleJobPage.vue',
    code: vueFile(`const timer = setTimeout(() => {}, 1)\nvoid timer`),
    violation: violates('タイマー', GLOBALS, 'window.setTimeout'),
  },
  {
    title: 'main.ts が素の setTimeout を使う',
    path: 'src/main.ts',
    code: `export const timer = setTimeout(() => {}, 1)\n`,
    violation: violates('タイマー', GLOBALS, 'window.setTimeout'),
  },
  {
    title: 'src の lib が globalThis.setTimeout を使う',
    path: 'src/admin/lib/sample.ts',
    code: `export const timer = globalThis.setTimeout(() => {}, 1)\n`,
    violation: violates('タイマー', PROPERTIES, 'window.setTimeout'),
  },
  {
    title: 'src の lib が globalThis.setInterval を使う',
    path: 'src/admin/lib/sample.ts',
    code: `export const timer = globalThis.setInterval(() => {}, 1)\n`,
    violation: violates('タイマー', PROPERTIES, 'window.setTimeout'),
  },
  {
    title: 'window.setTimeout は使ってよい(許される)',
    path: 'src/admin/lib/sample.ts',
    code: `export const timer = window.setTimeout(() => {}, 1)\n`,
  },
  {
    title: 'window.setInterval は使ってよい(許される)',
    path: 'src/admin/composables/sample.ts',
    code: `export const timer = window.setInterval(() => {}, 1)\n`,
  },
  {
    title: 'テストは素の setTimeout を使ってよい(許される)',
    path: 'src/admin/lib/sample.test.ts',
    code: `export const timer = setTimeout(() => {}, 1)\n`,
  },
  {
    title: 'tests/ は素の setTimeout を使ってよい(許される)',
    path: 'tests/support/sample.ts',
    code: `export const timer = setTimeout(() => {}, 1)\n`,
  },

  // ── テストの相対 import: admin/api の中身は禁止(公開口そのものは可)
  {
    title: 'テストが admin/api/errors を相対パスで import',
    path: 'tests/support/sample.ts',
    code: importing('../../src/admin/api/errors/toApiError'),
    violation: violates('R2', IMPORT, '相対パス'),
  },
  {
    title: 'テストが admin/api/index を相対パスで import',
    path: 'tests/support/sample.ts',
    code: importing('../../src/admin/api/index'),
    violation: violates('R2', IMPORT, '相対パス'),
  },
  {
    title: 'テストが公開口 admin/api 自身を相対パスで import(許される)',
    path: 'tests/support/sample.ts',
    code: importing('../../src/admin/api'),
  },

  // ── 未所属: ts 以外の拡張子も対象(scss・css・画像などは対象外)
  {
    title: '未所属の .mts',
    path: 'src/admin/foo/sample.mts',
    code: `export const a = 1\n`,
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
  {
    title: '未所属の .js',
    path: 'src/admin/lib/sample.js',
    code: `export const a = 1\n`,
    violation: violates('未所属', SYNTAX, 'ゾーン'),
  },
]

async function lintText(sample: Sample) {
  const [result] = await eslint.lintText(sample.code, { filePath: join(WEB_DIR, sample.path) })
  return result?.messages ?? []
}

describe('依存ルール(R1〜R17)の違反サンプル', () => {
  beforeAll(async () => {
    // ESLint の初期化(config の読み込みとパーサー)を、最初のテストの前に済ませる。
    await eslint.lintText('export const warmup = 1\n', {
      filePath: join(WEB_DIR, 'src/shared/lib/warmup.ts'),
    })
  })

  const violations = SAMPLES.filter((sample) => sample.violation)
  const allowed = SAMPLES.filter((sample) => !sample.violation)

  it.each(violations)('$violation.rule: $title', async (sample) => {
    const { ruleId, message } = sample.violation!

    const messages = await lintText(sample)

    expect(
      messages.some((m) => m.ruleId === ruleId && m.message.includes(message)),
      `${ruleId} / "${message}" が報告されるはず。実際: ${JSON.stringify(messages.map((m) => [m.ruleId, m.message]))}`,
    ).toBe(true)
  })

  it.each(allowed)('許される: $title', async (sample) => {
    const messages = await lintText(sample)

    expect(messages.map((m) => `${m.ruleId}: ${m.message}`)).toEqual([])
  })
})

// 代表的なパスごとに、ちょうど 1 つのゾーンに属すること(ゾーンが重ならない・抜けない)を確認する。
describe('ゾーンの所属', () => {
  const ZONE_KEY_PREFIX = 'loreley-zone:'
  const zonesOf = async (path: string) => {
    const config = await eslint.calculateConfigForFile(join(WEB_DIR, path))
    const settings = (config?.settings ?? {}) as Record<string, unknown>
    return Object.keys(settings)
      .filter((key) => key.startsWith(ZONE_KEY_PREFIX))
      .map((key) => key.slice(ZONE_KEY_PREFIX.length))
  }

  const EXPECTED_ZONE: [path: string, zone: string][] = [
    ['src/shared/theme/icons.ts', 'shared-theme-icons'],
    ['src/shared/theme/tokens.ts', 'shared-theme'],
    ['src/shared/theme/Sample.vue', 'shared-theme'],
    ['src/shared/ui/StatusTag.vue', 'shared-ui-vue'],
    ['src/shared/ui/statusMaps.ts', 'shared-ui-ts'],
    ['src/shared/api/apiError.ts', 'shared-api'],
    ['src/shared/lib/datetime.ts', 'shared-lib'],
    ['src/admin/api/client.ts', 'admin-api'],
    ['src/admin/api/errors/errorTable.ts', 'admin-api'],
    ['src/admin/lib/viewState.ts', 'admin-lib'],
    ['src/admin/lib/validation/rules.ts', 'admin-lib'],
    ['src/admin/lib/pagination.ts', 'admin-lib'],
    ['src/admin/queries/keys.ts', 'admin-queries'],
    ['src/admin/composables/useDebouncedRef.ts', 'admin-composables'],
    ['src/admin/queries/mutations/cancelJob.ts', 'admin-queries'],
    ['src/admin/composables/useListParams.ts', 'admin-composables'],
    ['src/admin/composables/useViewState.ts', 'admin-composables-use-view-state'],
    ['src/admin/components/data-table/AdminDataTable.vue', 'admin-components-vue'],
    ['src/admin/components/data-table/columns.ts', 'admin-components-ts'],
    ['src/admin/templates/ListPage.vue', 'admin-templates-vue'],
    ['src/admin/templates/sample.ts', 'admin-templates-ts'],
    ['src/admin/dialogs/crawl-start/CrawlStartDialog.vue', 'admin-dialogs-vue'],
    ['src/admin/dialogs/useOperationDialog.ts', 'admin-dialogs-ts'],
    ['src/admin/shell/AppShell.vue', 'admin-shell-vue'],
    ['src/admin/shell/externalLinks.ts', 'admin-shell-ts'],
    ['src/admin/features/dashboard/pages/DashboardPage.vue', 'admin-feature-dashboard-vue'],
    ['src/admin/features/sources/form/toRequest.ts', 'admin-feature-sources-ts'],
    ['src/admin/features/jobs/jobActions.ts', 'admin-feature-jobs-ts'],
    ['src/admin/features/documents/documentsParams.ts', 'admin-feature-documents-ts'],
    ['src/admin/features/opensearch/matrixModel.ts', 'admin-feature-opensearch-ts'],
    ['src/admin/router/routes.ts', 'admin-router'],
    ['src/admin/router/NotFoundPage.vue', 'admin-router'],
    // 型宣言(.d.ts)は、未所属の検査(unclassified)の例外だが、router の規則は適用される(`RouteMeta` の拡張)。
    ['src/admin/router/meta.d.ts', 'admin-router'],
    ['src/admin/router/guards.ts', 'admin-router'],
    ['src/admin/shell/navItems.ts', 'admin-shell-ts'],
    ['src/admin/shell/SideNav.vue', 'admin-shell-vue'],
    ['src/admin/composables/routeTitle.ts', 'admin-composables'],
    ['src/admin/templates/ViewStateBody.vue', 'admin-templates-vue'],
    ['src/admin/components/confirm-dialog/dialogLevel.ts', 'admin-components-ts'],
    ['src/shared/ui/useSnackbar.ts', 'shared-ui-ts'],
    ['src/admin/app/setupVuetify.ts', 'admin-app-setup-vuetify'],
    ['src/admin/app/setupQuery.ts', 'admin-app-setup-query'],
    ['src/admin/app/setupRouter.ts', 'admin-app'],
    ['src/admin/app/App.vue', 'admin-app'],
    ['src/main.ts', 'main'],
    ['src/admin/lib/viewState.test.ts', 'tests'],
    ['src/admin/api/errors/errorTable.contract.test.ts', 'tests'],
    ['tests/support/mount.ts', 'tests'],
    ['tests/e2e/shell.spec.ts', 'tests'],
    ['src/admin/foo/sample.ts', 'unclassified'],
    ['src/admin/features/sample.ts', 'unclassified'],
    ['src/admin/lib/Sample.vue', 'unclassified'],
  ]

  it.each(EXPECTED_ZONE)('%s は %s ゾーンだけに属する', async (path, zone) => {
    expect(await zonesOf(path)).toEqual([zone])
  })

  it('src の実ファイルは、すべてちょうど 1 つのゾーンに属し、未所属ではない', async () => {
    const srcDir = join(WEB_DIR, 'src')
    const files = (readdirSync(srcDir, { recursive: true }) as string[])
      .filter((file) => /\.(ts|vue)$/.test(file))
      .map((file) => relative(WEB_DIR, join(srcDir, file)))
    const targets = (
      await Promise.all(
        files.map(async (file) =>
          (await eslint.isPathIgnored(join(WEB_DIR, file))) || file.endsWith('.d.ts') ? null : file,
        ),
      )
    ).filter((file): file is string => file !== null)

    const zoneByFile = await Promise.all(targets.map(async (file) => [file, await zonesOf(file)]))

    expect(
      zoneByFile.filter(([, zones]) => zones.length !== 1 || zones[0] === 'unclassified'),
    ).toEqual([])
  })
})

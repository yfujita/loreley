// ESLint(flat config)。整形は Prettier だけが行うので、衝突する規則は eslint-config-prettier で無効にする。
//
// 依存ルール R1〜R17(docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.2.md 6 章)は
// `no-restricted-imports`・`no-restricted-globals`・`no-restricted-properties`・`no-restricted-syntax` で表す。
//
// flat config では、同じ規則を設定するブロックが複数あると、後のブロックのオプションが前のブロックを
// **置き換える**(マージされない)。そのため、ソースを「ゾーン」(ファイルの集合。互いに重ならない)に分け、
// 1 ファイルにつき規則を設定するブロックが 1 つだけになるようにしている。ゾーンを足すときは、
// 既存のゾーンと `files` が重ならないこと(重なるなら、既存側の `ignores` に足すこと)を守る。
import js from '@eslint/js'
import { defineConfig } from 'eslint/config'
import prettier from 'eslint-config-prettier'
import vue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

const FEATURES = ['dashboard', 'sources', 'jobs', 'documents', 'opensearch']

// `@/` は src の別名。`@/admin/lib` と `@/admin/lib/**` のように、モジュール名と配下を一組で扱う。
const MODULES = {
  sharedTheme: '@/shared/theme',
  sharedUi: '@/shared/ui',
  sharedApi: '@/shared/api',
  sharedLib: '@/shared/lib',
  api: '@/admin/api',
  lib: '@/admin/lib',
  queries: '@/admin/queries',
  composables: '@/admin/composables',
  components: '@/admin/components',
  templates: '@/admin/templates',
  dialogs: '@/admin/dialogs',
  shell: '@/admin/shell',
  router: '@/admin/router',
  app: '@/admin/app',
  ...Object.fromEntries(FEATURES.map((name) => [`feature-${name}`, `@/admin/features/${name}`])),
}
const ALL_MODULES = Object.keys(MODULES)
const SHARED_MODULES = ['sharedTheme', 'sharedUi', 'sharedApi', 'sharedLib']
const ALL_FEATURES = FEATURES.map((name) => `feature-${name}`)

const withChildren = (moduleName) => [moduleName, `${moduleName}/**`]

const TEST_FILES = ['**/*.test.ts', 'tests/**/*.ts']
const PARENT_RELATIVE_IMPORT = '(?:^|/)\\.\\.(?:/|$)'
// タイマーは `window.setTimeout`・`window.setInterval` で書く。`src/` の非テストには Node の型が効かないが、
// テストの型検査(tsconfig.test.json)では効くため、素の `setTimeout` は戻り値の型が環境で変わる(number と Timeout)。
const BARE_TIMER_NAMES = ['setTimeout', 'setInterval']
const BARE_TIMER_MESSAGE =
  'タイマーは window.setTimeout / window.setInterval で書きます(戻り値の型を number にそろえるため)。'
const SYNC_IMPORT_MESSAGE =
  '動的 import() と import.meta.glob は使いません(ルートはすべて同期 import。FMOD-P-17)。'
const GENERATED_DIR = 'src/admin/api/generated/'

/**
 * ゾーンの定義から、規則のオプションを組み立てる。
 *
 * - allow: import してよいモジュール(自分自身を含む)。ここにない `@/` のモジュールは禁止
 * - allowTypeOnly: `import type` だけ許すモジュール
 * - allowSubpaths: 禁止したモジュールのうち、例外として許す配下。{ モジュール名: [配下の名前] }(`queries/meta` など)
 * - vuetify: 'none' 全面禁止 / 'types' 型の import だけ可 / 'any' 部品は可(createVuetify と vuetify/styles は不可)
 *            / 'setup' すべて可(setupVuetify.ts) / 'main' vuetify/styles だけ可(main.ts)
 * - vueQuery: 'none' 禁止 / 'types' 型の import だけ可 / 'any' 可
 * - vue: 'any' 可 / 'types' 型の import だけ可
 * - banVueRouter: vue-router の import を禁止する
 * - allowHttp: fetch・XMLHttpRequest・@hey-api/*・文字列 '/api/admin/v1' を使ってよい(R3)
 * - allowMdiJs: @mdi/js を import してよい(R12)
 * - banVueFiles: `.vue` の import を禁止する(純粋なモジュール)
 * - allowGenerated: 生成コード(`@/admin/api/**`)を import してよい(admin/api の中だけ)
 * - rule: メッセージに出す依存ルールの番号(層の向きによる禁止の理由)
 * - unclassified: どのゾーンにも属さないファイル(ファイルがあること自体を違反にする)
 */
function buildRules(zone) {
  const {
    allow = [],
    allowTypeOnly = [],
    allowSubpaths = {},
    vuetify = 'none',
    vueQuery = 'none',
    vue: vueMode = 'any',
    banVueRouter = false,
    allowHttp = false,
    allowMdiJs = false,
    banVueFiles = false,
    allowGenerated = false,
    unclassified = false,
    rule = '層の向き',
  } = zone

  const restrictedModules = ALL_MODULES.filter(
    (name) => !allow.includes(name) && !allowTypeOnly.includes(name),
  )
  const patterns = []
  const paths = []

  const fullyRestricted = restrictedModules.filter((name) => !(name in allowSubpaths))
  if (fullyRestricted.length > 0) {
    patterns.push({
      group: fullyRestricted.flatMap((name) => withChildren(MODULES[name])),
      message: `依存ルール(${rule}): このゾーンから import できないモジュールです(設計 F 6 章。層の向きは 2.2)。`,
    })
  }
  // 配下の一部だけ許すモジュールは、否定のパターン(`!`)では書けない(親が除外されていると再許可されない)ので、
  // 「モジュール自身、または許す配下以外の配下」に一致する正規表現で書く。
  for (const [name, subpaths] of Object.entries(allowSubpaths)) {
    patterns.push({
      regex: `^${MODULES[name]}(?:/(?!(?:${subpaths.join('|')})(?:/|$)).*)?$`,
      message: `依存ルール(R9・R10): このゾーンは ${MODULES[name]} のうち ${subpaths.join('・')} だけ import できます。`,
    })
  }
  if (allowTypeOnly.length > 0) {
    patterns.push({
      group: allowTypeOnly.flatMap((name) => withChildren(MODULES[name])),
      allowTypeImports: true,
      message: '依存ルール(R5・R7): このモジュールからは型(import type)だけ import できます。',
    })
  }
  patterns.push({
    // `../x`・`./../x`・`..` のいずれも止める。
    regex: PARENT_RELATIVE_IMPORT,
    message:
      '層をまたぐ相対 import を避けるため、親ディレクトリへの相対 import は禁止です。`@/` を使ってください。',
  })
  if (banVueFiles) {
    patterns.push({
      group: ['**/*.vue'],
      message: '依存ルール(R5・R6): .vue は import できません。',
    })
  }
  // 公開口(`@/admin/api`)以外の深い import は禁止する(生成コードを含む。R2・E 11.1)。
  // api を丸ごと禁止するゾーンは、上のグループが掛かる(二重に報告しない)。
  if (!allowGenerated && !fullyRestricted.includes('api')) {
    patterns.push({
      group: ['@/admin/api/**'],
      message:
        '依存ルール(R2): 生成コードなど admin/api/ の中身は、外から直接 import しません。公開口 @/admin/api から。',
    })
  }
  if (!allowHttp) {
    patterns.push({
      group: ['@hey-api/*'],
      message: '依存ルール(R3): @hey-api/* は admin/api/ と shared/api/ の中だけです。',
    })
  }
  patterns.push({
    group: ['@mdi/font', '@mdi/font/**'],
    message:
      '依存ルール(R12): @mdi/font は使いません。アイコンは @mdi/js を shared/theme/icons.ts から。',
  })
  if (!allowMdiJs) {
    paths.push({
      name: '@mdi/js',
      message: '依存ルール(R12): @mdi/js は shared/theme/icons.ts だけで import します。',
    })
  }

  if (banVueRouter) {
    paths.push({
      name: 'vue-router',
      message: '依存ルール(R1・R5・R6・R7): このゾーンは vue-router を import できません。',
    })
  }
  if (vueMode === 'types') {
    paths.push({
      name: 'vue',
      allowTypeImports: true,
      message: '依存ルール(R5): admin/lib は vue の型(import type)だけ import できます。',
    })
  }
  if (vueQuery !== 'any') {
    paths.push({
      name: '@tanstack/vue-query',
      allowTypeImports: vueQuery === 'types',
      message:
        '依存ルール(R4): @tanstack/vue-query は admin/queries/ と admin/app/setupQuery.ts だけで import します。',
    })
  }

  const vuetifyMessage = '依存ルール(R13): このファイルは vuetify の部品を import できません。'
  if (vuetify === 'none' || vuetify === 'types') {
    const allowTypeImports = vuetify === 'types'
    paths.push({ name: 'vuetify', allowTypeImports, message: vuetifyMessage })
    patterns.push({ group: ['vuetify/**'], allowTypeImports, message: vuetifyMessage })
  }
  if (vuetify === 'any') {
    paths.push({
      name: 'vuetify',
      importNames: ['createVuetify'],
      message: '依存ルール(R13): createVuetify を呼ぶのは admin/app/setupVuetify.ts だけです。',
    })
    patterns.push({
      group: ['vuetify/styles'],
      message: '依存ルール(R13): vuetify/styles を import するのは main.ts だけです。',
    })
  }
  if (vuetify === 'main') {
    paths.push({ name: 'vuetify', message: vuetifyMessage })
    patterns.push({ group: ['vuetify/**', '!vuetify/styles'], message: vuetifyMessage })
  }

  const rules = {
    'no-restricted-imports': ['error', { paths, patterns }],
  }
  rules['no-restricted-globals'] = [
    'error',
    ...(allowHttp
      ? []
      : [
          {
            name: 'fetch',
            message: '依存ルール(R3): fetch は admin/api/ と shared/api/ の中だけで使います。',
          },
          {
            name: 'XMLHttpRequest',
            message:
              '依存ルール(R3): XMLHttpRequest は admin/api/ と shared/api/ の中だけで使います。',
          },
        ]),
    {
      name: 'process',
      message:
        'src/ はブラウザで動く。Node の API(process)は使いません(型は vite/client だけ。tsconfig.app.json)。',
    },
    {
      name: 'Buffer',
      message:
        'src/ はブラウザで動く。Node の API(Buffer)は使いません(型は vite/client だけ。tsconfig.app.json)。',
    },
    ...BARE_TIMER_NAMES.map((name) => ({ name, message: BARE_TIMER_MESSAGE })),
    {
      name: 'localStorage',
      message: '依存ルール(R14): ユーザー設定を持たないので、localStorage は使いません。',
    },
    {
      name: 'sessionStorage',
      message: '依存ルール(R14): ユーザー設定を持たないので、sessionStorage は使いません。',
    },
  ]
  rules['no-restricted-properties'] = [
    'error',
    // `window.setTimeout` は許す(戻り値が number)。`globalThis.*` は、テストの型検査(Node の型が効く)では Timeout になる。
    ...BARE_TIMER_NAMES.map((property) => ({
      object: 'globalThis',
      property,
      message: BARE_TIMER_MESSAGE,
    })),
    ...['window', 'globalThis'].flatMap((object) => [
      ...(allowHttp
        ? []
        : [
            {
              object,
              property: 'fetch',
              message: '依存ルール(R3): fetch は admin/api/ と shared/api/ の中だけで使います。',
            },
            {
              object,
              property: 'XMLHttpRequest',
              message:
                '依存ルール(R3): XMLHttpRequest は admin/api/ と shared/api/ の中だけで使います。',
            },
          ]),
      { object, property: 'localStorage', message: '依存ルール(R14): localStorage は使いません。' },
      {
        object,
        property: 'sessionStorage',
        message: '依存ルール(R14): sessionStorage は使いません。',
      },
    ]),
  ]
  // 動的 import と import.meta.glob は使わない(ルートはすべて同期 import。FMOD-P-17)。
  const syntaxRules = [
    { selector: 'ImportExpression', message: SYNC_IMPORT_MESSAGE },
    {
      selector:
        "CallExpression > MemberExpression.callee[object.type='MetaProperty'][property.name=/^glob(Eager)?$/]",
      message: SYNC_IMPORT_MESSAGE,
    },
  ]
  if (!allowHttp) {
    const message =
      "依存ルール(R3): '/api/admin/v1' は admin/api/ と shared/api/ の中だけに書きます。"
    syntaxRules.push(
      { selector: 'Literal[value=/\\/api\\/admin\\/v1/]', message },
      { selector: 'TemplateElement[value.raw=/\\/api\\/admin\\/v1/]', message },
    )
  }
  if (unclassified) {
    syntaxRules.push({
      selector: 'Program',
      message:
        'このファイルは eslint.config.js のどのゾーンにも属しません。新しいディレクトリ・ファイルは、依存ルールのゾーン(sourceZones)に足してください。',
    })
  }
  rules['no-restricted-syntax'] = ['error', ...syntaxRules]
  return rules
}

/** テストと tests/ に適用する規則(F 6 章): R2 と、R3 のうち fetch・XMLHttpRequest の呼び出しと @hey-api/* の import の禁止だけ。 */
function buildTestRules() {
  return {
    'no-restricted-imports': [
      'error',
      {
        patterns: [
          {
            group: ['@/admin/api/**'],
            message:
              '依存ルール(R2): テストでも生成コードなど admin/api/ の中身を直接 import しません。型は @/admin/api(公開口)から。',
          },
          {
            // `../../src/admin/api/errors/…` や `…/generated/…` のような相対パスでの回避も止める(公開口 `…/admin/api` 自身は可)。
            // admin/api の中の `./generated` などは、`admin/api` を含まないので対象外。
            regex: '(?:^|/)admin/api/.',
            message:
              '依存ルール(R2): テストでも admin/api/ の中身を相対パスで直接 import しません。公開口 @/admin/api から。',
          },
          {
            group: ['@hey-api/*'],
            message: '依存ルール(R3): テストでも @hey-api/* を import しません。',
          },
        ],
      },
    ],
    // 動的 import() は no-restricted-imports の対象外なので、生成コードへの直接 import だけ別に止める。
    'no-restricted-syntax': [
      'error',
      {
        selector: 'ImportExpression[source.value=/(^|\\/)admin\\/api\\//]',
        message:
          '依存ルール(R2): テストでも生成コードなど admin/api/ の中身を直接 import しません。',
      },
    ],
    // fetch の差し替え(globalThis.fetch = …)は呼び出しではないので、プロパティは検査しない。
    'no-restricted-globals': [
      'error',
      {
        name: 'fetch',
        message: '依存ルール(R3): テストでも fetch を直接呼びません(差し替えは fetchStub)。',
      },
      {
        name: 'XMLHttpRequest',
        message: '依存ルール(R3): テストでも XMLHttpRequest を使いません。',
      },
    ],
  }
}

/**
 * ゾーン: ソースのファイルの集合と、その規則。`files` は互いに重ならないようにする。
 * `.vue` と `.ts` で vuetify の扱いが違うゾーン(R13)は、2 つに分ける。
 */
// ゾーン名の先頭 → そのゾーンが他のモジュールを import できない理由の依存ルール番号(F 6 章)。
const RULE_BY_ZONE = [
  ['shared-', 'R1'],
  ['admin-api', 'R17'],
  ['admin-lib', 'R5'],
  ['admin-queries', 'R6'],
  ['admin-composables', 'R16'],
  ['admin-components', 'R7'],
  ['admin-templates', 'R7'],
  ['admin-dialogs', 'R9'],
  ['admin-shell', 'R10'],
  ['admin-feature-', 'R8'],
  ['admin-router', 'R11'],
  ['admin-app', 'R15'],
  ['main', 'R15'],
]

function sourceZone(name, files, spec, ignores = []) {
  const rule = RULE_BY_ZONE.find(([prefix]) => name.startsWith(prefix))?.[1]
  return {
    name: `loreley/zone/${name}`,
    files,
    ignores: [...TEST_FILES, GENERATED_DIR + '**', ...ignores],
    // ゾーンの所属を確認するテスト(dependencyRules.test.ts)が読む。重なると、印が複数付く。
    settings: { [`loreley-zone:${name}`]: true },
    rules: buildRules({ ...spec, rule }),
  }
}

const vueFiles = (dir) => [`${dir}/**/*.vue`]
const tsFiles = (dir) => [`${dir}/**/*.ts`]

// 層の向き(下の層だけを import する)。同じ層どうしは、規則に書いたもの以外は禁止。
const BELOW_COMPONENTS = ['lib', 'composables', ...SHARED_MODULES]

// vuetify の部品を import してよいのは、.vue(と shared/theme・app の一部)だけ(R13)。
const vuetifyVueOnly = (name, dir, spec) => [
  sourceZone(`${name}-vue`, vueFiles(dir), { ...spec, vuetify: 'any' }),
  sourceZone(`${name}-ts`, tsFiles(dir), { ...spec, vuetify: 'types' }),
]

const sourceZones = [
  // ── 層 0: shared(R1: admin/・vue-router・vue-query・生成コードを import しない)
  sourceZone('shared-theme-icons', ['src/shared/theme/icons.ts'], {
    allow: SHARED_MODULES,
    vuetify: 'any',
    banVueRouter: true,
    allowMdiJs: true,
  }),
  sourceZone(
    'shared-theme',
    ['src/shared/theme/**/*.{ts,vue}'],
    { allow: SHARED_MODULES, vuetify: 'any', banVueRouter: true },
    ['src/shared/theme/icons.ts'],
  ),
  ...vuetifyVueOnly('shared-ui', 'src/shared/ui', { allow: SHARED_MODULES, banVueRouter: true }),
  sourceZone('shared-api', ['src/shared/api/**/*.ts'], {
    allow: ['sharedApi', 'sharedLib'],
    banVueRouter: true,
    allowHttp: true,
    banVueFiles: true,
  }),
  sourceZone('shared-lib', ['src/shared/lib/**/*.ts'], {
    allow: ['sharedLib'],
    banVueRouter: true,
    banVueFiles: true,
  }),

  // ── 層 1: admin/api(R17: shared/api と自分の generated だけ。R3: HTTP の入口)
  sourceZone('admin-api', ['src/admin/api/**/*.ts'], {
    allow: ['api', 'sharedApi'],
    allowHttp: true,
    allowGenerated: true,
    banVueFiles: true,
  }),
  // ── 層 1: admin/lib(R5: 純粋。型は公開口 @/admin/api から可)
  sourceZone('admin-lib', ['src/admin/lib/**/*.ts'], {
    allow: ['lib', ...SHARED_MODULES],
    allowTypeOnly: ['api'],
    vue: 'types',
    banVueRouter: true,
    banVueFiles: true,
  }),

  // ── 層 2: admin/queries(R6: UI を知らない)
  sourceZone('admin-queries', ['src/admin/queries/**/*.ts'], {
    allow: ['queries', 'api', 'lib', 'sharedApi', 'sharedLib'],
    vueQuery: 'any',
    banVueRouter: true,
    banVueFiles: true,
  }),
  // ── 層 2: admin/composables(R16。vue-query の型は useViewState.ts だけ)
  sourceZone(
    'admin-composables',
    ['src/admin/composables/**/*.ts'],
    { allow: ['composables', 'api', 'lib', ...SHARED_MODULES], banVueFiles: true },
    ['src/admin/composables/useViewState.ts'],
  ),
  sourceZone('admin-composables-use-view-state', ['src/admin/composables/useViewState.ts'], {
    allow: ['composables', 'api', 'lib', ...SHARED_MODULES],
    vueQuery: 'types',
    banVueFiles: true,
  }),

  // ── 層 3: admin/components・admin/templates(R7: データ取得を知らない。api は型だけ)
  ...vuetifyVueOnly('admin-components', 'src/admin/components', {
    allow: ['components', ...BELOW_COMPONENTS],
    allowTypeOnly: ['api'],
    banVueRouter: true,
  }),
  ...vuetifyVueOnly('admin-templates', 'src/admin/templates', {
    allow: ['templates', ...BELOW_COMPONENTS],
    allowTypeOnly: ['api'],
    banVueRouter: true,
  }),

  // ── 層 4: admin/dialogs(R9)・admin/shell(R10)
  // 設計 1.2 の「主な入力」と R9・R10 に合わせて絞っている(dialogs は queries(書き込み)・components・api・lib・composables、
  // shell は composables・queries/meta・lib と api の型)。R9・R10 が禁止を明記せず、層の向き(F 2.2)でも許されるものは許す。
  ...vuetifyVueOnly('admin-dialogs', 'src/admin/dialogs', {
    allow: ['dialogs', 'api', 'components', 'composables', 'lib', ...SHARED_MODULES],
    // R9: queries は mutations だけ。
    allowSubpaths: { queries: ['mutations'] },
  }),
  ...vuetifyVueOnly('admin-shell', 'src/admin/shell', {
    allow: ['shell', 'composables', 'lib', ...SHARED_MODULES],
    allowTypeOnly: ['api'],
    // R10: queries は meta だけ。
    allowSubpaths: { queries: ['meta'] },
  }),

  // ── 層 5: admin/features/<A>(R8: 他の features・router・app を import しない)
  ...FEATURES.flatMap((name) =>
    vuetifyVueOnly(`admin-feature-${name}`, `src/admin/features/${name}`, {
      allow: [
        `feature-${name}`,
        'queries',
        'api',
        'components',
        'templates',
        'dialogs',
        ...BELOW_COMPONENTS,
      ],
    }),
  ),

  // ── 層 6: admin/router(R11: features のページ・templates(404)・lib だけ。queries・shell・app は import しない)
  // vuetify は R13 の列挙に無いので、.vue も含めて import しない(404 ページは shared/ui の部品を使う)。
  sourceZone('admin-router', ['src/admin/router/**/*.{ts,vue}'], {
    // composables は、ガードのタイトル更新などで使う(FMOD-U-10)。R11 が禁止していない。
    allow: ['router', 'templates', 'composables', 'lib', ...ALL_FEATURES, ...SHARED_MODULES],
  }),

  // ── 層 7: admin/app(R4: vue-query は setupQuery.ts だけ。R13: vuetify・createVuetify は setupVuetify.ts だけ)
  sourceZone('admin-app-setup-vuetify', ['src/admin/app/setupVuetify.ts'], {
    allow: ALL_MODULES,
    vuetify: 'setup',
  }),
  sourceZone('admin-app-setup-query', ['src/admin/app/setupQuery.ts'], {
    allow: ALL_MODULES,
    vueQuery: 'any',
  }),
  sourceZone('admin-app', ['src/admin/app/**/*.{ts,vue}'], { allow: ALL_MODULES }, [
    'src/admin/app/setupVuetify.ts',
    'src/admin/app/setupQuery.ts',
  ]),

  // ── main.ts(R15: admin/app を import するのは main.ts だけ。vuetify/styles は main.ts だけ)
  sourceZone('main', ['src/main.ts'], {
    allow: ['app', 'api', ...SHARED_MODULES],
    vuetify: 'main',
  }),
]

// どのゾーンにも属さない src のファイル(新しいディレクトリ・想定外の置き場所)は、最も厳しい規則(`allow: []`)を
// 適用したうえで、ファイルがあること自体を違反にする。ゾーンを足し忘れても、検査の抜けにならない。
// 意図的な例外: テスト・生成コード・型宣言(.d.ts)。
const unclassifiedZone = {
  name: 'loreley/zone/unclassified',
  files: ['src/**/*.{ts,tsx,mts,cts,js,mjs,cjs,vue}'],
  ignores: [
    ...sourceZones.flatMap((zone) => zone.files),
    ...TEST_FILES,
    GENERATED_DIR + '**',
    '**/*.d.ts',
  ],
  settings: { 'loreley-zone:unclassified': true },
  rules: buildRules({
    allow: [],
    banVueRouter: true,
    banVueFiles: true,
    unclassified: true,
    rule: '未所属',
  }),
}

export default defineConfig([
  {
    name: 'loreley/ignores',
    ignores: ['dist/', GENERATED_DIR, 'openapi/', 'test-results/', 'playwright-report/'],
  },
  js.configs.recommended,
  tseslint.configs.recommended,
  vue.configs['flat/recommended'],
  {
    name: 'loreley/base',
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    name: 'loreley/base-rules',
    files: ['**/*.{ts,vue}'],
    rules: {
      // 型検査(vue-tsc)が未定義の識別子を検出する。
      'no-undef': 'off',
      // verbatimModuleSyntax: `import { type X } from '…'` は副作用 import(`import '…'`)として残る。
      '@typescript-eslint/no-import-type-side-effects': 'error',
      'vue/multi-word-component-names': ['error', { ignores: ['App'] }],
    },
  },
  ...sourceZones,
  unclassifiedZone,
  {
    name: 'loreley/zone/tests',
    files: TEST_FILES,
    settings: { 'loreley-zone:tests': true },
    rules: buildTestRules(),
  },
  prettier,
])

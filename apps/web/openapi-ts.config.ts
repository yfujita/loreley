import { resolve } from 'node:path'

import { defineConfig } from '@hey-api/openapi-ts'

// LORELEY_GEN_OUT は、入力と出力の基点ディレクトリ(既定は apps/web)。
// `npm run gen:api:check` が一時ディレクトリへ生成して作業ツリーと比べるために切り替える。
const baseDir = resolve(process.env.LORELEY_GEN_OUT ?? '.')

export default defineConfig({
  input: resolve(baseDir, 'openapi/admin-v1.json'),
  output: resolve(baseDir, 'src/admin/api/generated'),
  plugins: [
    '@hey-api/client-fetch',
    '@hey-api/typescript',
    '@hey-api/sdk',
    // 既定だと page を持つ EP-09・11 に *InfiniteOptions が出る(内部に @ts-ignore・as any を含む)。
    // MVP は通常のページ送りなので生成しない。
    { name: '@tanstack/vue-query', infiniteQueryOptions: false },
  ],
})

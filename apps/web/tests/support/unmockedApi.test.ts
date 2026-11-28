import { describe, expect, it } from 'vitest'

import { isApiRequestUrl } from './unmockedApi'

describe('isApiRequestUrl', () => {
  it.each([
    'http://localhost:15173/api/admin/v1/meta',
    'http://localhost:15173/api/admin/v1/jobs?page=1',
    'http://127.0.0.1:8090/api/anything',
  ])('API の URL は対象になる: %s', (url) => {
    expect(isApiRequestUrl(url)).toBe(true)
  })

  it.each([
    // Vite の dev サーバーが返すモジュール。パスの途中に `/api/` を含むが、API ではない。
    'http://localhost:15173/admin/src/admin/api/generated/client.gen.ts',
    'http://localhost:15173/admin/src/admin/api/index.ts',
    'http://localhost:15173/admin/node_modules/.vite/deps/api.js',
    'http://localhost:15173/admin/',
    'http://localhost:15173/admin/sources',
    'http://localhost:15173/apidocs/x',
    'http://localhost:15173/api',
  ])('API ではない URL は対象にならない: %s', (url) => {
    expect(isApiRequestUrl(url)).toBe(false)
  })
})

// 契約テスト(E 10.1・F 7.2): コミット済みの OpenAPI JSON(`openapi/admin-v1.json`)の各 EP の `responses` の
// 説明文(`Conflict. error.code: a, b` の書式)から code を集め、手書きの errorTable と突き合わせる。
// OpenAPI で `ErrorBody.code` は string で列挙がなく、code は説明文にしか出ないため。
// JSON は「再生成して差分ゼロ」(`gen:api:check`)で実装と一致が保たれるので、実行時に API は呼ばない。
// 説明文の書式が変わるとこのテストが落ちる(それで検出してよい)。
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { ADMIN_ERROR_CODES, COMMON_ERROR_CODES, ERROR_TABLE } from './errorTable'

type OpenApiDocument = {
  paths: Record<
    string,
    Record<string, { operationId: string; responses: Record<string, { description?: string }> }>
  >
}

const OPENAPI_PATH = resolve(import.meta.dirname, '../../../../openapi/admin-v1.json')
const document = JSON.parse(readFileSync(OPENAPI_PATH, 'utf-8')) as OpenApiDocument

const ERROR_CODE_PATTERN = /error\.code: ([a-z_]+(?:, [a-z_]+)*)\s*$/

/** OpenAPI の説明文に出る code → それを返す EP の operationId。 */
function collectCodesFromDescriptions(): Map<string, Set<string>> {
  const codes = new Map<string, Set<string>>()
  for (const methods of Object.values(document.paths)) {
    for (const operation of Object.values(methods)) {
      for (const [status, response] of Object.entries(operation.responses)) {
        const match = ERROR_CODE_PATTERN.exec(response.description ?? '')
        if (match === null) {
          // 説明文に code がないのは成功応答だけ(エラー応答で書式が変わったら検出する)。
          expect(Number(status), `${operation.operationId} ${status}`).toBeLessThan(300)
          continue
        }
        for (const code of match[1]!.split(', ')) {
          const operations = codes.get(code) ?? new Set<string>()
          operations.add(operation.operationId)
          codes.set(code, operations)
        }
      }
    }
  }
  return codes
}

describe('errorTable ↔ OpenAPI の description', () => {
  const codesInOpenApi = collectCodesFromDescriptions()

  it('OpenAPI の説明文に出る code は、Admin 固有 14 種 + invalid_request・unavailable の計 16 種', () => {
    expect([...codesInOpenApi.keys()].sort()).toEqual(
      [...ADMIN_ERROR_CODES, 'invalid_request', 'unavailable'].sort(),
    )
    expect(codesInOpenApi.size).toBe(16)
  })

  it('(1) OpenAPI に出る code は、すべて errorTable にある', () => {
    for (const code of codesInOpenApi.keys()) {
      expect(ERROR_TABLE, `OpenAPI の code ${code} が errorTable にない`).toHaveProperty(code)
    }
  })

  it('(2) errorTable の Admin 固有 14 種は、OpenAPI のどれかの説明文に出る', () => {
    for (const code of ADMIN_ERROR_CODES) {
      expect(codesInOpenApi.has(code), `${code} が OpenAPI の説明文にない`).toBe(true)
    }
  })

  it('共通 6 種のうち OpenAPI に宣言がない 4 種(not_found など)は、表の側だけで網羅する', () => {
    const commonNotInOpenApi = COMMON_ERROR_CODES.filter((code) => !codesInOpenApi.has(code))

    expect([...commonNotInOpenApi].sort()).toEqual([
      'http_error',
      'internal_error',
      'method_not_allowed',
      'not_found',
    ])
    for (const code of commonNotInOpenApi) expect(ERROR_TABLE).toHaveProperty(code)
  })

  it('EP と code の対応が B 2.3 の EP 列と一致する(代表)', () => {
    expect([...(codesInOpenApi.get('lock_held') ?? [])].sort()).toEqual([
      'start_crawl',
      'start_source_delete',
    ])
    expect([...(codesInOpenApi.get('lock_in_use') ?? [])]).toEqual(['release_lock'])
    expect([...(codesInOpenApi.get('job_already_finished') ?? [])]).toEqual(['cancel_job'])
    expect([...(codesInOpenApi.get('source_already_exists') ?? [])]).toEqual(['register_source'])
    expect([...(codesInOpenApi.get('config_invalid') ?? [])].sort()).toEqual([
      'register_source',
      'update_source',
    ])
  })
})

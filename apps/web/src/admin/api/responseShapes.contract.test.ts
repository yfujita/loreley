// 契約テスト(OpenAPI ↔ responseShapes.ts): 表が、コミット済みの OpenAPI(`openapi/admin-v1.json`)から外れたら落ちる。
// - OpenAPI の全 2xx 応答に、表のエントリがある(表に余分な EP もない)
// - 表の項目が OpenAPI の required に含まれ、型(string・number・boolean・object・array)と null 許容が一致する
// - 配列の要素の項目・オブジェクトの中の項目も、同じ規則で一致する(EP-11 の行のような anyOf は、どの型の行でも成り立つこと)
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { RESPONSE_SHAPES, type FieldKind, type ResponseShape } from './responseShapes'

type Schema = {
  $ref?: string
  type?: string
  anyOf?: Schema[]
  items?: Schema
  properties?: Record<string, Schema>
  required?: string[]
}
type OpenApiDocument = {
  paths: Record<
    string,
    Record<string, { responses: Record<string, { content?: Record<string, { schema: Schema }> }> }>
  >
  components: { schemas: Record<string, Schema> }
}

const document = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../../../openapi/admin-v1.json'), 'utf-8'),
) as OpenApiDocument

function deref(schema: Schema): Schema {
  if (schema.$ref === undefined) return schema
  const name = schema.$ref.split('/').pop()!
  return document.components.schemas[name]!
}

/** OpenAPI のプロパティの種類を、表の FieldKind の書き方にする(`|null` は anyOf に null があるとき)。 */
function kindOf(property: Schema): string {
  const variants = property.anyOf ?? [property]
  const nullable = variants.some((variant) => variant.type === 'null')
  const bases = new Set(
    variants
      .filter((variant) => variant.type !== 'null')
      .map((variant) => {
        const resolved = deref(variant)
        if (resolved.type === 'integer' || resolved.type === 'number') return 'number'
        return resolved.type ?? 'unknown'
      }),
  )
  const base = [...bases].join('/')
  return nullable ? `${base}|null` : base
}

/** 2xx 応答の本文のスキーマ(`メソッド url` → スキーマ)。EP-03 の 200・201 のように複数の 2xx は、同じ本文型。 */
function successSchemas(): Map<string, Schema[]> {
  const result = new Map<string, Schema[]>()
  for (const [path, methods] of Object.entries(document.paths)) {
    for (const [method, operation] of Object.entries(methods)) {
      for (const [status, response] of Object.entries(operation.responses)) {
        if (!status.startsWith('2')) continue
        // 204・205(本文なし)は Admin API の契約にない。宣言されたら、client.ts の「204・205 は異常」の前提が崩れる。
        if (status === '204' || status === '205') {
          throw new Error(
            `${method} ${path} が ${status} を宣言しました(client.ts の validateSuccessResponse を見直す)`,
          )
        }
        const schema = response.content?.['application/json']?.schema
        if (schema === undefined)
          throw new Error(`${method} ${path} ${status} に JSON の本文がありません`)
        const key = `${method.toUpperCase()} ${path}`
        result.set(key, [...(result.get(key) ?? []), deref(schema)])
      }
    }
  }
  return result
}

function checkFields(
  where: string,
  spec: Readonly<Record<string, FieldKind>>,
  schemas: Schema[],
): void {
  for (const schema of schemas) {
    for (const [key, kind] of Object.entries(spec)) {
      const property = schema.properties?.[key]
      expect(property, `${where}.${key} が OpenAPI にない`).toBeDefined()
      expect(schema.required ?? [], `${where}.${key} が required でない`).toContain(key)
      expect(kindOf(property!), `${where}.${key} の型・null 許容が OpenAPI と違う`).toBe(kind)
    }
  }
}

/** 配列の項目の、要素のスキーマ(anyOf のときは、すべての型)。 */
function elementSchemas(array: Schema): Schema[] {
  const items = array.items!
  return (items.anyOf ?? [items]).map(deref)
}

describe('responseShapes ↔ OpenAPI', () => {
  const successes = successSchemas()

  it('OpenAPI の全 2xx 応答に表のエントリがあり、表に余分なエントリもない', () => {
    expect([...Object.keys(RESPONSE_SHAPES)].sort()).toEqual([...successes.keys()].sort())
  })

  // 204・205 の宣言は successSchemas が拒否する(収集の時点で、宣言した EP を名指しして落ちる)。
  it('OpenAPI の 2xx は 16 件(200・201・202 を含む)', () => {
    expect([...successes.values()].flat()).toHaveLength(16)
  })

  it.each(Object.entries(RESPONSE_SHAPES))('%s', (key, shape: ResponseShape) => {
    const schemas = successes.get(key)!

    checkFields(key, shape.fields, schemas)
    for (const [field, spec] of Object.entries(shape.nested ?? {})) {
      const objectProperties = schemas.map((schema) => deref(schema.properties![field]!))
      checkFields(`${key}.${field}`, spec, objectProperties)
    }
    for (const [field, spec] of Object.entries(shape.elements ?? {})) {
      for (const schema of schemas) {
        const array = schema.properties![field]!
        expect(array.type, `${key}.${field} が OpenAPI で配列でない`).toBe('array')
        checkFields(`${key}.${field}[]`, spec, elementSchemas(array))
      }
    }
  })
})

// 2xx 応答の最小限の形の検査(E 5.3・F 3.3)。
//
// 生成型は応答を型どおりと信じるが、プロキシの誤配信・API の不具合・版のずれで、型と違う JSON が 2xx で届きうる
// (例: Dashboard が `{"status":"ok"}`)。そのまま成功として Query に載せると、画面の view model が実行時例外になり、
// エラー表示の仕組みに載らない。ここで、**画面の描画と管理操作の成功判定に使う項目だけ**を検査し、満たさなければ
// `invalid_response`(status つき)にする。全項目の厳密な検証(スキーマの完全な検証)ではない。
//
// 表は手書きで、OpenAPI との整合は responseShapes.contract.test.ts が担保する(全 2xx 応答に項目があること、
// 項目が OpenAPI の required で、型と null 許容が一致すること)。
//
// 検査する項目は、nullable でない(null を許さない)ものと、画面が null と undefined を区別して使うもの(`|null`)に限る。
// 値は検査しても、診断・エラーメッセージには含めない。

/** 項目の種類。`|null` は「キーが必ずあり、値は null でもよい」。 */
export type FieldKind =
  'string' | 'number' | 'boolean' | 'object' | 'array' | 'string|null' | 'number|null'

type FieldSpec = Readonly<Record<string, FieldKind>>

export type ResponseShape = {
  /** 最上位の項目 */
  fields: FieldSpec
  /** 配列の項目ごとの、各要素(オブジェクト)の項目 */
  elements?: Readonly<Record<string, FieldSpec>>
  /** オブジェクトの項目ごとの、その中の項目 */
  nested?: Readonly<Record<string, FieldSpec>>
}

const NUMBER = 'number'
const STRING = 'string'

/** キーは `メソッド 生成 SDK の url`(パスのテンプレート。`/jobs/{job_id}` など。パス値を含まない)。 */
export const RESPONSE_SHAPES: Readonly<Record<string, ResponseShape>> = {
  // ── EP-01・02(S1・S2)
  'GET /sources': {
    fields: { items: 'array', unavailable: 'object' },
    elements: { items: { source_id: STRING, unavailable: 'object' } },
  },
  'GET /sources/{source_id}': {
    fields: { source_id: STRING, index: 'object', unavailable: 'object' },
  },
  // ── EP-03・04(S3・S4 の保存。成功したら `source_id` の S2 へ遷移する)
  'POST /sources': { fields: { source_id: STRING, status: STRING } },
  'PUT /sources/{source_id}': { fields: { source_id: STRING, status: STRING } },
  // ── EP-05・06(受付。スナックバーと J2 への遷移に `job_id` を使う)
  'POST /sources/{source_id}/crawl-jobs': { fields: { job_id: STRING, source_id: STRING } },
  'POST /sources/{source_id}/delete-jobs': { fields: { job_id: STRING, source_id: STRING } },
  // ── EP-07(取消。文言は `status` で分岐する)
  'POST /jobs/{job_id}/cancel': { fields: { job_id: STRING, status: STRING } },
  // ── EP-08(ロック解放。`released=false` は成功の文言にしない)
  'DELETE /sources/{source_id}/lock': { fields: { source_id: STRING, released: 'boolean' } },
  // ── EP-09・10(J1・J2)
  'GET /jobs': {
    fields: {
      items: 'array',
      total: NUMBER,
      page: NUMBER,
      items_per_page: NUMBER,
      window_limit: NUMBER,
      unavailable: 'object',
    },
    elements: {
      items: { job_id: STRING, source_id: STRING, cancellable: 'boolean', unavailable: 'object' },
    },
  },
  'GET /jobs/{job_id}': {
    fields: {
      job_id: STRING,
      source_id: STRING,
      cancellable: 'boolean',
      cancel_after_finish_notice: 'boolean',
      warnings: 'array',
      unavailable: 'object',
    },
    // `warnings[]` の要素は、オブジェクトであること(中身の `code` は features が型ガードで読む)
    elements: { warnings: {} },
  },
  // ── EP-11(X1)。行は判別子のない 4 型で、どの型の行も `unavailable` を持つ
  'GET /sources/{source_id}/documents': {
    fields: {
      items: 'array',
      tab: STRING,
      total: NUMBER,
      page: NUMBER,
      items_per_page: NUMBER,
      window_limit: NUMBER,
      tab_counts: 'object',
      unavailable: 'object',
    },
    elements: { items: { unavailable: 'object' } },
  },
  // ── EP-12(O1)。マトリクス・概況・警告が反復・参照する項目
  'GET /opensearch/cluster': {
    fields: {
      cluster: 'object',
      indices: 'array',
      nodes: 'array',
      shards: 'array',
      truncated: 'boolean',
      total_indices: NUMBER,
      fetched_at: STRING,
    },
    nested: {
      cluster: {
        name: STRING,
        status: STRING,
        node_count: NUMBER,
        active_shards: NUMBER,
        relocating_shards: NUMBER,
        initializing_shards: NUMBER,
        unassigned_shards: NUMBER,
      },
    },
    elements: {
      nodes: { name: STRING },
      indices: { name: STRING, status: 'string|null', document_count: 'number|null' },
      // `node` は未割り当てのとき null。キーがないものを「未割り当て」と取り違えないよう、キーの存在を検査する
      shards: { index: STRING, shard: NUMBER, role: STRING, state: STRING, node: 'string|null' },
    },
  },
  // ── EP-13(D1)。タイルが参照する項目
  'GET /dashboard': {
    fields: { components: 'array', checked_at: STRING },
    elements: {
      components: { id: STRING, state: STRING, checked_at: STRING, reason: 'string|null' },
    },
  },
  // ── EP-14(シェル)。項目はすべて nullable で、画面は欠落を null と同じに扱う
  'GET /meta': { fields: {} },
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function matchesKind(value: unknown, kind: FieldKind): boolean {
  const [base, nullable] = kind.split('|') as [string, string | undefined]
  if (value === null) return nullable === 'null'
  switch (base) {
    case 'string':
      return typeof value === 'string'
    case 'number':
      return typeof value === 'number' && Number.isFinite(value)
    case 'boolean':
      return typeof value === 'boolean'
    case 'object':
      return isRecord(value)
    case 'array':
      return Array.isArray(value)
    default:
      return false
  }
}

function findFieldProblem(
  record: Record<string, unknown>,
  spec: FieldSpec,
  path: string,
): string | null {
  for (const [key, kind] of Object.entries(spec)) {
    const at = path === '' ? key : `${path}.${key}`
    if (!Object.hasOwn(record, key)) return `${at} がありません(期待: ${kind})`
    if (!matchesKind(record[key], kind)) return `${at} の型が違います(期待: ${kind})`
  }
  return null
}

/** 本文(パース済みの JSON)が表の形を満たさないとき、最初の問題を返す(値は含めない)。満たせば null。 */
export function findShapeProblem(shape: ResponseShape, data: unknown): string | null {
  if (!isRecord(data)) return '本文が JSON のオブジェクトではありません'

  const top = findFieldProblem(data, shape.fields, '')
  if (top !== null) return top

  for (const [key, spec] of Object.entries(shape.nested ?? {})) {
    const nested = data[key]
    if (!isRecord(nested)) return `${key} がオブジェクトではありません`
    const problem = findFieldProblem(nested, spec, key)
    if (problem !== null) return problem
  }

  for (const [key, spec] of Object.entries(shape.elements ?? {})) {
    const items = data[key]
    if (!Array.isArray(items)) return `${key} が配列ではありません`
    for (const [index, item] of items.entries()) {
      if (!isRecord(item)) return `${key}[${index}] がオブジェクトではありません`
      const problem = findFieldProblem(item, spec, `${key}[${index}]`)
      if (problem !== null) return problem
    }
  }
  return null
}

/** 2xx の応答の形が表と合わないとき(または想定外の 204・205)に、response interceptor が投げる。 */
export class ResponseShapeError extends Error {
  constructor(problem: string) {
    super(`unexpected response: ${problem}`)
    this.name = 'ResponseShapeError'
  }
}

import { describe, expect, it } from 'vitest'

import { dashboard } from '../../../tests/support/fixtures/dashboard'
import { documents } from '../../../tests/support/fixtures/documents'
import {
  jobAccepted,
  jobDetails,
  jobList,
  releaseLockResponses,
} from '../../../tests/support/fixtures/jobs'
import { meta } from '../../../tests/support/fixtures/meta'
import { opensearch } from '../../../tests/support/fixtures/opensearch'
import { savedSettings, sourceDetails, sourceList } from '../../../tests/support/fixtures/sources'
import { findShapeProblem, RESPONSE_SHAPES } from './responseShapes'

const shape = (key: string) => RESPONSE_SHAPES[key]!

describe('findShapeProblem: 形の合ったフィクスチャ(生成型で satisfies した正常な応答)は通る', () => {
  it.each([
    ['GET /sources', sourceList.normal()],
    ['GET /sources', sourceList.empty()],
    ['GET /sources/{source_id}', sourceDetails.normal()],
    ['GET /sources/{source_id}', sourceDetails.lockUnavailable()],
    ['POST /sources', savedSettings.registered()],
    ['PUT /sources/{source_id}', savedSettings.updated()],
    ['POST /sources/{source_id}/crawl-jobs', jobAccepted.crawl()],
    ['POST /sources/{source_id}/delete-jobs', jobAccepted.sourceDelete()],
    ['POST /jobs/{job_id}/cancel', { job_id: 'job-3', status: 'running' }],
    ['DELETE /sources/{source_id}/lock', releaseLockResponses.notReleased()],
    ['GET /jobs', jobList.normal()],
    ['GET /jobs', jobList.statusNull()],
    ['GET /jobs/{job_id}', jobDetails.succeeded()],
    ['GET /jobs/{job_id}', jobDetails.warnings()],
    ['GET /sources/{source_id}/documents', documents.skipped()],
    ['GET /sources/{source_id}/documents', documents.oversize()],
    ['GET /sources/{source_id}/documents', documents.empty()],
    ['GET /opensearch/cluster', opensearch.green()],
    ['GET /opensearch/cluster', opensearch.yellow()],
    ['GET /opensearch/cluster', opensearch.nullIndexValues()],
    ['GET /opensearch/cluster', opensearch.empty()],
    ['GET /dashboard', dashboard.allNormal()],
    ['GET /dashboard', dashboard.abnormal()],
    ['GET /meta', meta.normal()],
    ['GET /meta', meta.noDashboards()],
  ])('%s', (key, body) => {
    expect(findShapeProblem(shape(key), body)).toBeNull()
  })
})

describe('findShapeProblem: 形の合わない応答(表駆動)', () => {
  const cluster = opensearch.green()
  const cases: Array<[name: string, key: string, body: unknown, problem: RegExp]> = [
    // 全体
    ['{"status":"ok"}(Dashboard)', 'GET /dashboard', { status: 'ok' }, /components/],
    ['本文が配列', 'GET /dashboard', [], /オブジェクトではありません/],
    ['本文が null', 'GET /meta', null, /オブジェクトではありません/],
    ['本文が文字列', 'GET /sources', 'ok', /オブジェクトではありません/],
    // 配列であるべき項目
    [
      'components が配列でない',
      'GET /dashboard',
      { checked_at: 'x', components: {} },
      /components.*array/,
    ],
    ['items が配列でない', 'GET /sources', { items: null, unavailable: {} }, /items.*array/],
    [
      'indices が配列でない',
      'GET /opensearch/cluster',
      { ...cluster, indices: {} },
      /indices.*array/,
    ],
    ['nodes がない', 'GET /opensearch/cluster', { ...cluster, nodes: undefined }, /nodes/],
    ['shards が null', 'GET /opensearch/cluster', { ...cluster, shards: null }, /shards/],
    [
      'warnings が配列でない',
      'GET /jobs/{job_id}',
      { ...jobDetails.succeeded(), warnings: {} },
      /warnings/,
    ],
    // 要素
    [
      '要素がオブジェクトでない',
      'GET /dashboard',
      { checked_at: 'x', components: [null] },
      /components\[0\]/,
    ],
    [
      '要素に id がない',
      'GET /dashboard',
      { checked_at: 'x', components: [{ state: 'normal', checked_at: 'x', reason: null }] },
      /components\[0\]\.id/,
    ],
    [
      '要素の reason のキーがない',
      'GET /dashboard',
      { checked_at: 'x', components: [{ id: 'api', state: 'normal', checked_at: 'x' }] },
      /reason/,
    ],
    [
      '2 番目の要素だけ不正',
      'GET /jobs',
      { ...jobList.normal(), items: [jobList.normal().items[0], { job_id: 'x' }] },
      /items\[1\]/,
    ],
    [
      'shards の要素に node のキーがない',
      'GET /opensearch/cluster',
      { ...cluster, shards: [{ index: 'a', shard: 0, role: 'primary', state: 'started' }] },
      /shards\[0\]\.node/,
    ],
    [
      '行に unavailable がない(EP-11)',
      'GET /sources/{source_id}/documents',
      { ...documents.skipped(), items: [{ document_id: 'x' }] },
      /items\[0\]\.unavailable/,
    ],
    [
      'warnings の要素がオブジェクトでない',
      'GET /jobs/{job_id}',
      { ...jobDetails.succeeded(), warnings: ['x'] },
      /warnings\[0\]/,
    ],
    // 型違い
    [
      'cluster の件数が文字列',
      'GET /opensearch/cluster',
      { ...cluster, cluster: { ...cluster.cluster, node_count: '1' } },
      /cluster\.node_count/,
    ],
    [
      'cluster がオブジェクトでない',
      'GET /opensearch/cluster',
      { ...cluster, cluster: [] },
      /cluster/,
    ],
    [
      'truncated が文字列',
      'GET /opensearch/cluster',
      { ...cluster, truncated: 'false' },
      /truncated/,
    ],
    ['total が NaN 相当(null)', 'GET /jobs', { ...jobList.normal(), total: null }, /total/],
    [
      'cancellable が文字列',
      'GET /jobs',
      { ...jobList.normal(), items: [{ ...jobList.normal().items[0], cancellable: 'yes' }] },
      /cancellable/,
    ],
    // 書き込みの成功判定
    [
      '受付に job_id がない',
      'POST /sources/{source_id}/crawl-jobs',
      { status: 'queued' },
      /job_id/,
    ],
    [
      '受付の job_id が数値',
      'POST /sources/{source_id}/delete-jobs',
      { ...jobAccepted.sourceDelete(), job_id: 1 },
      /job_id/,
    ],
    ['取消に status がない', 'POST /jobs/{job_id}/cancel', { job_id: 'j' }, /status/],
    [
      'ロック解放に released がない',
      'DELETE /sources/{source_id}/lock',
      { source_id: 'a' },
      /released/,
    ],
    [
      'ロック解放の released が文字列',
      'DELETE /sources/{source_id}/lock',
      { source_id: 'a', released: 'true' },
      /released/,
    ],
    ['保存に source_id がない', 'POST /sources', { status: 'active' }, /source_id/],
  ]

  it.each(cases)('%s', (_name, key, body, problem) => {
    expect(findShapeProblem(shape(key), body)).toMatch(problem)
  })

  it('メッセージに値を含めない(入力値・パスを診断に出さない)', () => {
    const problem = findShapeProblem(shape('GET /dashboard'), {
      checked_at: 'SECRET-VALUE',
      components: 'SECRET-VALUE',
    })

    expect(problem).not.toContain('SECRET-VALUE')
  })

  it('null 許容(`|null`)の項目は、null なら通り、キーがないと落ちる', () => {
    const noReason = {
      checked_at: 'x',
      components: [{ id: 'api', state: 'normal', checked_at: 'x', reason: null }],
    }

    expect(findShapeProblem(shape('GET /dashboard'), noReason)).toBeNull()
  })

  it('プロトタイプのキー(constructor など)を、項目があると誤判定しない', () => {
    // shape が 'constructor' を要求するわけではないが、hasOwn で見ていること(`in` ではない)を、キーの欠落で確かめる
    const body = Object.create({ components: [], checked_at: 'x' }) as unknown

    expect(findShapeProblem(shape('GET /dashboard'), body)).toMatch(/components/)
  })
})

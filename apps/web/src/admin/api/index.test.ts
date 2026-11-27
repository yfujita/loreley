// 公開口(`@/admin/api`)の export を固定する(F 3.3)。
// 出さないもの: 生成の `client`・SDK 関数(Query・mutation 経由だけ。E 5.3)、`{fn}QueryKey`(key は queries の key factory)、
// EP 側の型 `{Op}Response`・`{Op}Response2`(スキーマ名の型だけを使う。5.2)、`{Op}Data`・`{Op}Responses`・`{Op}Errors`。
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import * as api from '@/admin/api'
import type * as ApiTypes from '@/admin/api'

describe('公開口の値の export', () => {
  it('Options 8 + Mutation 6 + configureApiClient・describeError・isValidPathId・isApiError だけ', () => {
    expect(Object.keys(api).sort()).toEqual(
      [
        // 読み取り(EP-01・02・09〜14)
        'getClusterOptions',
        'getDashboardOptions',
        'getJobOptions',
        'getMetaOptions',
        'getSourceOptions',
        'listDocumentsOptions',
        'listJobsOptions',
        'listSourcesOptions',
        // 書き込み(EP-03〜08)
        'cancelJobMutation',
        'registerSourceMutation',
        'releaseLockMutation',
        'startCrawlMutation',
        'startSourceDeleteMutation',
        'updateSourceMutation',
        // 設定・検証・エラー
        'configureApiClient',
        'describeError',
        'isApiError',
        'isValidPathId',
      ].sort(),
    )
  })

  it('生成の client・SDK 関数・QueryKey を出さない', () => {
    const exported = Object.keys(api)

    expect(exported).not.toContain('client')
    for (const sdkFunction of [
      'listSources',
      'getSource',
      'registerSource',
      'updateSource',
      'startSourceDelete',
      'startCrawl',
      'cancelJob',
      'releaseLock',
      'listJobs',
      'getJob',
      'listDocuments',
      'getCluster',
      'getDashboard',
      'getMeta',
    ]) {
      expect(exported, sdkFunction).not.toContain(sdkFunction)
    }
    expect(exported.filter((name) => name.endsWith('QueryKey'))).toEqual([])
  })
})

describe('公開口の型の export', () => {
  it('EP 側の型({Op}Response・{Op}Response2・Data・Responses・Errors)を出さない(型検査で確認する)', () => {
    // @ts-expect-error {Op}Response2 は出さない
    type A = ApiTypes.CancelJobResponse2
    // @ts-expect-error {Op}Response2 は出さない
    type B = ApiTypes.ReleaseLockResponse2
    // @ts-expect-error EP 側の {Op}Response は出さない(スキーマ名の型を使う)
    type C = ApiTypes.GetMetaResponse
    // @ts-expect-error EP 側の {Op}Response は出さない
    type D = ApiTypes.ListJobsResponse
    // @ts-expect-error {Op}Data は admin/api の中だけ
    type E = ApiTypes.GetJobData
    // @ts-expect-error {Op}Errors は admin/api の中だけ
    type F = ApiTypes.GetJobErrors
    // @ts-expect-error {Op}Responses は admin/api の中だけ
    type G = ApiTypes.GetJobResponses
    // @ts-expect-error 生成のクライアント設定の型
    type H = ApiTypes.ClientOptions
    // 使われない型の宣言(型検査のためだけ)
    const unused: [A?, B?, C?, D?, E?, F?, G?, H?] = []
    expect(unused).toEqual([])
  })

  it('スキーマ名の型は出す(CancelJobResponse・ReleaseLockResponse・SourceSettings ほか)', () => {
    const names: [
      ApiTypes.CancelJobResponse?,
      ApiTypes.ReleaseLockResponse?,
      ApiTypes.SourceSettings?,
      ApiTypes.SourceDetailResponse?,
      ApiTypes.JobDetailResponse?,
      ApiTypes.StartCrawlBody?,
      ApiTypes.ApiError?,
    ] = []
    expect(names).toEqual([])
  })

  it('index.ts のソースに、SDK 関数・{fn}QueryKey・Response2 の再 export がない', () => {
    const source = readFileSync(resolve(import.meta.dirname, 'index.ts'), 'utf-8')
      .split('\n')
      .filter((line) => !line.trim().startsWith('//'))
      .join('\n')

    expect(source).not.toMatch(/Response2/)
    expect(source).not.toMatch(/QueryKey/)
    expect(source).not.toMatch(/sdk\.gen/)
    expect(source).not.toMatch(/client\.gen/)
  })
})

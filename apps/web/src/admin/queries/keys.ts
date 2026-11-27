// key factory(E 5.4・F 3.4)。生成の `{fn}QueryKey` は使わず、ドメインごとの key で上書きする。
// 理由: DS 4.3・admin-view 7.11 の key の書き方(`['sources', …]`)に合わせ、invalidate を prefix で意図どおり指定でき、
// Hey API 0.x の key の形の変更に引きずられない。
//
// `params`(条件)は、URL から正規化した型付きの条件。JSON にできる値だけで作る(key の同一性は JSON で決まる)。
import type { DocumentsQuery } from '@/admin/queries/documents'
import type { JobsQuery } from '@/admin/queries/jobs'

export const keys = {
  meta: () => ['meta'] as const,
  dashboard: () => ['dashboard'] as const,
  sources: {
    /** invalidate の prefix(一覧・詳細・編集のすべて) */
    all: ['sources'] as const,
    list: () => ['sources', 'list'] as const,
    detail: (sourceId: string) => ['sources', 'detail', sourceId] as const,
    edit: (sourceId: string) => ['sources', 'edit', sourceId] as const,
  },
  jobs: {
    all: ['jobs'] as const,
    list: (params: JobsQuery) => ['jobs', 'list', params] as const,
    detail: (jobId: string) => ['jobs', 'detail', jobId] as const,
  },
  documents: {
    all: ['documents'] as const,
    list: (sourceId: string | null, params: DocumentsQuery) =>
      ['documents', sourceId, params] as const,
  },
  opensearch: {
    all: ['opensearch'] as const,
    cluster: () => ['opensearch', 'cluster'] as const,
  },
}

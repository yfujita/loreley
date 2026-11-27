// route 名の定数(F 3.5・admin-view 4.2)。features が `routes.ts` を import せずに遷移できるようにする(循環を避ける。R8)。
export const ROUTE_NAMES = {
  dashboard: 'dashboard',
  sources: 'sources',
  sourceNew: 'source-new',
  sourceDetail: 'source-detail',
  sourceEdit: 'source-edit',
  jobs: 'jobs',
  jobDetail: 'job-detail',
  documents: 'documents',
  opensearch: 'opensearch',
  notFound: 'not-found',
} as const

export type RouteName = (typeof ROUTE_NAMES)[keyof typeof ROUTE_NAMES]

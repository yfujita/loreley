// route の定義(admin-view 4.2 の表をそのまま。DS 5.3)。ナビ項目・パンくず・タイトル・テンプレートは `meta` にだけ持つ。
// ページはすべて同期 import(単一チャンク。FMOD-P-17)。`/sources/new` は `/sources/:sourceId` より先に定義する。
import type { RouteRecordRaw } from 'vue-router'

import DashboardPage from '@/admin/features/dashboard/pages/DashboardPage.vue'
import DocumentsPage from '@/admin/features/documents/pages/DocumentsPage.vue'
import JobDetailPage from '@/admin/features/jobs/pages/JobDetailPage.vue'
import JobsListPage from '@/admin/features/jobs/pages/JobsListPage.vue'
import OpenSearchPage from '@/admin/features/opensearch/pages/OpenSearchPage.vue'
import SourceCreatePage from '@/admin/features/sources/pages/SourceCreatePage.vue'
import SourceDetailPage from '@/admin/features/sources/pages/SourceDetailPage.vue'
import SourceEditPage from '@/admin/features/sources/pages/SourceEditPage.vue'
import SourcesListPage from '@/admin/features/sources/pages/SourcesListPage.vue'
import { ROUTE_NAMES } from '@/admin/lib/routeNames'
import {
  mdiDatabaseOutline,
  mdiFileSearchOutline,
  mdiPlaylistCheck,
  mdiServer,
  mdiViewDashboardOutline,
} from '@/shared/theme/icons'

import NotFoundPage from './NotFoundPage.vue'

/** パスの値(`:sourceId` など)を文字列にする。vue-router が復号済みの値で、繰り返しのパラメータは使わない。 */
function paramText(value: string | string[] | undefined): string {
  return Array.isArray(value) ? value.join('/') : (value ?? '')
}

export const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: ROUTE_NAMES.dashboard,
    component: DashboardPage,
    meta: {
      title: 'ダッシュボード',
      template: 'dashboard',
      nav: { label: 'ダッシュボード', icon: mdiViewDashboardOutline, group: 'overview', order: 0 },
    },
  },
  {
    path: '/sources',
    name: ROUTE_NAMES.sources,
    component: SourcesListPage,
    meta: {
      title: 'データソース',
      template: 'list',
      nav: { label: 'データソース', icon: mdiDatabaseOutline, group: 'operate', order: 0 },
    },
  },
  {
    path: '/sources/new',
    name: ROUTE_NAMES.sourceNew,
    component: SourceCreatePage,
    meta: { title: 'データソースを登録', template: 'form', parent: ROUTE_NAMES.sources },
  },
  {
    path: '/sources/:sourceId',
    name: ROUTE_NAMES.sourceDetail,
    component: SourceDetailPage,
    meta: {
      title: (route) => paramText(route.params.sourceId),
      template: 'detail',
      parent: ROUTE_NAMES.sources,
    },
  },
  {
    path: '/sources/:sourceId/edit',
    name: ROUTE_NAMES.sourceEdit,
    component: SourceEditPage,
    meta: { title: '編集', template: 'form', parent: ROUTE_NAMES.sourceDetail },
  },
  {
    path: '/jobs',
    name: ROUTE_NAMES.jobs,
    component: JobsListPage,
    meta: {
      title: 'ジョブ',
      template: 'list',
      nav: { label: 'ジョブ', icon: mdiPlaylistCheck, group: 'operate', order: 1 },
    },
  },
  {
    path: '/jobs/:jobId',
    name: ROUTE_NAMES.jobDetail,
    component: JobDetailPage,
    meta: {
      title: (route) => paramText(route.params.jobId),
      template: 'detail',
      parent: ROUTE_NAMES.jobs,
    },
  },
  {
    path: '/documents',
    name: ROUTE_NAMES.documents,
    component: DocumentsPage,
    meta: {
      title: '文書の確認',
      template: 'list',
      nav: { label: '文書の確認', icon: mdiFileSearchOutline, group: 'inspect', order: 0 },
    },
  },
  {
    path: '/opensearch',
    name: ROUTE_NAMES.opensearch,
    component: OpenSearchPage,
    meta: {
      title: 'OpenSearch',
      template: 'dashboard',
      nav: { label: 'OpenSearch', icon: mdiServer, group: 'inspect', order: 1 },
    },
  },
  // 未定義のパス(SPA 内の 404)。最後に定義する。Nginx は `/admin/` 配下の未知のパスに index.html を返すので、ここで描く。
  {
    path: '/:pathMatch(.*)*',
    name: ROUTE_NAMES.notFound,
    component: NotFoundPage,
    meta: { title: 'ページが見つかりません', template: 'list' },
  },
]

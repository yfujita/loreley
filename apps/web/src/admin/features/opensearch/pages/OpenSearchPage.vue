<script setup lang="ts">
// O1 OpenSearch(AF-17。opensearch 画面仕様)。1 つのカード「クラスタ状態」: 概況 → 絞り込みフォーム → マトリクス。
// 読み取り専用。操作は「更新」(手動のみ。自動更新はしない)と、表示するインデックスの絞り込み。
//
// 状態はカード内の領域単位で出す(読み込み中・エラー(データなし)・空は、見出し「クラスタ状態」を残してカードの中に出す)。
// そのため、テンプレートの状態の出し分けは使わず(`READY_VIEW_STATE`)、`ViewStateBody` を 2 つ重ねる:
// 外側は stale のアラートだけ(ページ上部)、内側(カードの中)は読み込み中・エラーのブロックだけ。
import { computed, useId } from 'vue'

import ClusterSummary from '@/admin/components/shard-matrix/ClusterSummary.vue'
import IndexFilter from '@/admin/components/shard-matrix/IndexFilter.vue'
import ShardMatrix from '@/admin/components/shard-matrix/ShardMatrix.vue'
import { useRouteTitle } from '@/admin/composables/useRouteTitle'
import { READY_VIEW_STATE, type ViewState } from '@/admin/lib/viewState'
import { ROUTE_NAMES } from '@/admin/lib/routeNames'
import DashboardPageTemplate from '@/admin/templates/DashboardPage.vue'
import ViewStateBody from '@/admin/templates/ViewStateBody.vue'
import { formatCount } from '@/shared/lib/number'
import { mdiRefresh } from '@/shared/theme/icons'
import PageAlert from '@/shared/ui/PageAlert.vue'
import StateBlock from '@/shared/ui/StateBlock.vue'
import TimeText from '@/shared/ui/TimeText.vue'
import TopProgress from '@/shared/ui/TopProgress.vue'

import { useOpenSearchPage } from '@/admin/features/opensearch/composables/useOpenSearchPage'
import { formatShardNumbers } from '@/admin/features/opensearch/models/clusterNotices'

const title = useRouteTitle()
const {
  viewState,
  response,
  params,
  filtering,
  conditionText,
  conditionKey,
  matrix,
  unassignedPrimaries,
  setName,
  setStates,
  clearCondition,
  refresh,
} = useOpenSearchPage()

const DESCRIPTION =
  'OpenSearch のクラスタ状態(クラスタの概況と、インデックスごとのドキュメント件数・シャードの配置)を確認します。この画面は読み取り専用で、インデックスの削除・シャードの再配置・設定の変更はできません。'
const TEXTS = {
  loadingLabel: 'OpenSearch の状態を読み込み中',
  errorTitle: 'OpenSearch の状態を取得できません',
  errorMessage:
    'OpenSearch に接続できなかったか、応答が返りませんでした。しばらくしてから再試行してください。解消しない場合は、ダッシュボードで opensearch と api の状態を確認してください。',
  staleNote: 'クラスタの現在の状態と異なる可能性があります。',
}
/** red のアラートに並べるインデックスの上限(数百のインデックスが同時に red になっても、ページを埋めない) */
const MAX_ALERT_INDICES = 10

const cardTitleId = useId()
const isLoading = computed(() => viewState.value.kind === 'loading')
const isStale = computed(() => viewState.value.kind === 'stale')

// 外側: stale のアラートだけ。内側: 読み込み中・エラーだけ(stale は内側では通常の表示)。
function withKind(kind: ViewState['kind']): ViewState {
  return { ...viewState.value, kind, isRefreshing: false }
}
const outerState = computed(() => withKind(isStale.value ? 'stale' : 'ready'))
const innerState = computed(() =>
  withKind(['loading', 'error'].includes(viewState.value.kind) ? viewState.value.kind : 'ready'),
)

const hasNoIndices = computed(() => response.value?.indices.length === 0)
const shownPrimaries = computed(() => unassignedPrimaries.value.slice(0, MAX_ALERT_INDICES))
const hiddenPrimaryCount = computed(
  () => unassignedPrimaries.value.length - shownPrimaries.value.length,
)
const singlePrimary = computed(() =>
  unassignedPrimaries.value.length === 1 ? unassignedPrimaries.value[0] : undefined,
)
</script>

<template>
  <DashboardPageTemplate
    :title="title"
    :description="DESCRIPTION"
    :view-state="READY_VIEW_STATE"
    testid-prefix="o1"
  >
    <template #aside>
      <div class="o1-page__acts">
        <span v-if="viewState.updatedAt !== null" class="text-caption-sm text-on-surface-variant">
          最終更新 <TimeText :value="viewState.updatedAt" with-seconds />
        </span>
        <v-btn variant="outlined" size="small" :prepend-icon="mdiRefresh" @click="refresh">
          更新
        </v-btn>
      </div>
    </template>

    <ViewStateBody :view-state="outerState" :texts="TEXTS" card @retry="refresh">
      <PageAlert
        v-if="unassignedPrimaries.length > 0"
        type="error"
        role="status"
        title="未割り当てのプライマリシャードがあります"
      >
        <p v-if="singlePrimary !== undefined">
          {{ singlePrimary.index }} のプライマリシャード({{
            formatShardNumbers(singlePrimary.shardNumbers)
          }})が割り当てられていません。このインデックスの検索や登録に影響する可能性があります。
        </p>
        <template v-else>
          <p>該当するインデックスの検索や登録に影響する可能性があります。</p>
          <ul class="o1-page__alert-list">
            <li v-for="item in shownPrimaries" :key="item.index">
              {{ item.index }}({{ formatShardNumbers(item.shardNumbers) }})
            </li>
          </ul>
          <p v-if="hiddenPrimaryCount > 0">ほか {{ hiddenPrimaryCount }} 件のインデックス</p>
        </template>
      </PageAlert>

      <v-card
        tag="section"
        class="o1-page__card"
        :aria-labelledby="cardTitleId"
        :aria-busy="isLoading ? 'true' : undefined"
        data-testid="o1-cluster"
      >
        <TopProgress :active="isLoading || viewState.isRefreshing" />
        <div class="o1-page__card-head">
          <h2 :id="cardTitleId" class="text-section-title">クラスタ状態</h2>
          <!-- h2 の外の別要素にする(カードのアクセシブルネームに連結させない) -->
          <span
            v-if="isStale"
            class="text-caption-sm text-on-surface-variant"
            data-testid="o1-state-stale"
          >
            前回取得時の値 · 最終更新(成功) <TimeText :value="viewState.updatedAt" with-seconds />
          </span>
        </div>

        <ViewStateBody
          :view-state="innerState"
          :texts="TEXTS"
          testid-prefix="o1"
          :heading-level="3"
          @retry="refresh"
        >
          <template #loading>
            <p class="sr-only" role="status" data-testid="o1-state-loading">
              {{ TEXTS.loadingLabel }}
            </p>
            <div class="o1-page__skeleton">
              <span class="skeleton-line" style="width: 30%" />
              <span class="skeleton-line" style="width: 20%" />
              <span class="skeleton-line" style="width: 60%" />
            </div>
            <IndexFilter :name="params.q" :states="params.states" :has-condition="false" disabled />
            <div class="o1-page__skeleton">
              <span class="skeleton-line" style="width: 80%" />
              <span class="skeleton-line" style="width: 70%" />
              <span class="skeleton-line" style="width: 75%" />
            </div>
          </template>
          <template #error-actions>
            <v-btn variant="text" :to="{ name: ROUTE_NAMES.dashboard }">ダッシュボードを開く</v-btn>
          </template>

          <template v-if="response !== undefined && matrix !== null">
            <PageAlert v-if="response.truncated" type="warning" class="o1-page__truncated">
              インデックスが多いため先頭
              {{ formatCount(response.indices.length) }} 件だけを表示しています(全
              {{ formatCount(response.total_indices) }} 件)。
            </PageAlert>
            <ClusterSummary :cluster="response.cluster" :stale="isStale" />
            <StateBlock
              v-if="hasNoIndices"
              kind="empty"
              title="インデックスがありません"
              message="このクラスタにはインデックスが作成されていません。インデックスが作成されると、ここに、インデックスごとのドキュメント件数とシャードの配置が表示されます。"
              :heading-level="3"
              data-testid="o1-state-empty"
            />
            <template v-else>
              <IndexFilter
                :name="params.q"
                :states="params.states"
                :has-condition="filtering"
                @update:name="setName"
                @update:states="setStates"
                @clear="clearCondition"
              />
              <ShardMatrix
                :model="matrix"
                :total-index-count="response.indices.length"
                :filtered="filtering"
                :condition-text="conditionText"
                :reset-key="conditionKey"
              />
            </template>
          </template>
        </ViewStateBody>
      </v-card>
    </ViewStateBody>
  </DashboardPageTemplate>
</template>

<style scoped>
.o1-page__acts {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}
.o1-page__card {
  position: relative;
  overflow: hidden;
}
.o1-page__card-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 4px 16px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.o1-page__card-head h2 {
  margin: 0;
}
.o1-page__skeleton {
  display: grid;
  gap: 12px;
  padding: 16px;
}
.o1-page__truncated {
  margin: 12px 16px;
}
.o1-page__alert-list {
  margin: 4px 0 0;
  padding-left: 1.5em;
}
</style>

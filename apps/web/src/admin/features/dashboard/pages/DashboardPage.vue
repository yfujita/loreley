<script setup lang="ts">
// D1 ダッシュボード(AF-18。dashboard 画面仕様)。各コンポーネントの死活を、概況バーとタイルで見せる。
// 読み取り専用。操作は「更新」と「自動更新」の入切だけ。
import AutoRefreshSwitch from '@/admin/components/auto-refresh-switch/AutoRefreshSwitch.vue'
import ComponentTile from '@/admin/components/dashboard-parts/ComponentTile.vue'
import SummaryBand from '@/admin/components/dashboard-parts/SummaryBand.vue'
import { useRouteTitle } from '@/admin/composables/useRouteTitle'
import { DASHBOARD_POLL_INTERVAL_MS } from '@/admin/queries/polling'
import DashboardPageTemplate from '@/admin/templates/DashboardPage.vue'
import { mdiRefresh } from '@/shared/theme/icons'
import TimeText from '@/shared/ui/TimeText.vue'

import { useDashboardPage } from '@/admin/features/dashboard/composables/useDashboardPage'

const title = useRouteTitle()
const { autoRefresh, viewState, viewModel, manualUpdateMessage, refresh, retry } =
  useDashboardPage()

const DESCRIPTION =
  '各コンポーネントが起動して応答できるかを確認します。現在の状態だけを表示し、履歴や推移は記録しません。'
const TEXTS = {
  loadingLabel: 'コンポーネントの状態を読み込み中',
  errorTitle: 'コンポーネントの状態を取得できません',
  errorMessage:
    'Admin API に接続できませんでした。しばらくしてから再試行してください。解消しない場合は、api コンテナが起動しているかを確認してください。',
}
const POLL_INTERVAL_SECONDS = DASHBOARD_POLL_INTERVAL_MS / 1000
const SKELETON_TILES = 3
</script>

<template>
  <DashboardPageTemplate
    :title="title"
    :description="DESCRIPTION"
    :view-state="viewState"
    :texts="TEXTS"
    testid-prefix="d1"
    @retry="retry"
  >
    <template #toolbar>
      <span v-if="viewState.updatedAt !== null" class="text-caption-sm text-on-surface-variant">
        最終取得成功 <TimeText :value="viewState.updatedAt" with-seconds />
      </span>
      <AutoRefreshSwitch v-model="autoRefresh" :interval-seconds="POLL_INTERVAL_SECONDS" />
      <v-btn variant="outlined" size="small" :prepend-icon="mdiRefresh" @click="refresh">
        更新
      </v-btn>
    </template>

    <template v-if="viewModel !== null">
      <SummaryBand :model="viewModel.summary" />

      <section class="dashboard-page__group">
        <h2 class="text-section-title">コンポーネント</h2>
        <ul class="dashboard-page__tiles" aria-label="コンポーネントの状態">
          <ComponentTile v-for="tile in viewModel.required" :key="tile.id" :model="tile" />
        </ul>
      </section>

      <section class="dashboard-page__group">
        <h2 class="text-section-title">任意のコンポーネント</h2>
        <ul class="dashboard-page__tiles" aria-label="任意のコンポーネントの状態">
          <ComponentTile v-for="tile in viewModel.optional" :key="tile.id" :model="tile" />
        </ul>
      </section>

      <section class="dashboard-page__note" aria-labelledby="d1-note-title">
        <h2 id="d1-note-title" class="text-section-title">この表示について</h2>
        <ul class="text-caption-sm text-on-surface-variant">
          <li>
            各コンポーネントが起動を終えて、応答できるかを確認した結果です。ジョブが止まっていないかは、「ジョブ」で確認してください。
          </li>
          <li>
            「判定不能」は、確認そのものが失敗して状態が分からないことを示します。コンポーネントが落ちている「異常」とは別です。確認結果が古いときも、「正常」とは表示しません。
          </li>
        </ul>
      </section>
    </template>

    <!-- 前回の「状態」を、いまの状態として読ませない(dashboard 4.3) -->
    <template #stale-message>
      <p>
        Admin API
        に接続できないため、どのコンポーネントの現在の状態も確認できません。前回取得した状態(<TimeText
          :value="viewState.updatedAt"
          with-seconds
        />
        時点)を、タイルに添えています。
      </p>
    </template>

    <template #loading>
      <div class="dashboard-page__loading" aria-busy="true" data-testid="d1-state-loading">
        <p class="sr-only" role="status">{{ TEXTS.loadingLabel }}</p>
        <div class="dashboard-page__skeleton">
          <span class="skeleton-line" style="width: 40%; height: 18px" />
          <span class="skeleton-line" style="width: 60%" />
        </div>
        <ul class="dashboard-page__tiles" aria-hidden="true">
          <li v-for="n in SKELETON_TILES" :key="n" class="dashboard-page__skeleton">
            <span class="skeleton-line" style="width: 50%" />
            <span class="skeleton-line" style="width: 80%" />
            <span class="skeleton-line" style="width: 40%" />
          </li>
        </ul>
      </div>
    </template>
  </DashboardPageTemplate>

  <!-- 手動の「更新」の結果だけを読み上げる(自動更新の結果は読み上げない) -->
  <p class="sr-only" role="status">{{ manualUpdateMessage }}</p>
</template>

<style scoped>
/* 見出しとタイルを 1 組にして、見出しとリストの間隔(12px)を内側の gap で決める。組の上は、ほかのブロックより 8px 広く空ける */
.dashboard-page__group {
  display: grid;
  gap: 12px;
  margin-top: 8px;
}
.dashboard-page__group h2 {
  margin: 0;
}
/* 最小幅 240px の auto-fill・余白 16px(DS 6.4) */
.dashboard-page__tiles {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  margin: 0;
  padding: 0;
  list-style: none;
}
.dashboard-page__note {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  overflow: hidden;
}
.dashboard-page__note h2 {
  margin: 0;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.dashboard-page__note ul {
  display: grid;
  gap: 4px;
  margin: 0;
  padding: 14px 16px;
  list-style: none;
}
.dashboard-page__note li {
  display: flex;
  gap: 8px;
}
.dashboard-page__note li::before {
  content: '・';
  flex: none;
}
.dashboard-page__loading {
  display: grid;
  gap: 16px;
  min-width: 0;
}
.dashboard-page__skeleton {
  display: grid;
  gap: 10px;
  padding: 16px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
</style>

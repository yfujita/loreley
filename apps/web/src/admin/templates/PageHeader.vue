<script setup lang="ts">
// ページ見出し領域(DS 5.1・6): パンくず(inject)・`h1`・状態タグ・説明・操作。
// `h1` は `tabindex="-1"`: 遷移後に router の `afterEach` がフォーカスを移す(DS 8)。
// パンくずは `AppShell` が provide する(`templates`(層 3)は `shell`(層 4)を import しない。F 3.7)。
import { inject, ref } from 'vue'

import type { ActionSpec } from '@/admin/lib/actions'
import { breadcrumbsKey } from '@/admin/lib/injectionKeys'

import PageActions from './PageActions.vue'
import PageBreadcrumbs from './PageBreadcrumbs.vue'

defineProps<{
  title: string
  /** 識別子(`source_id`・ジョブ ID)を見出しにするとき、等幅にする */
  monoTitle?: boolean
  description?: string
  actions?: readonly ActionSpec[]
  primaryActionId?: string | null
}>()

const emit = defineEmits<{ action: [id: string] }>()

const breadcrumbs = inject(breadcrumbsKey, ref([]))
</script>

<template>
  <header class="page-header">
    <PageBreadcrumbs :items="breadcrumbs" />
    <div class="page-header__row">
      <div class="page-header__main">
        <h1 tabindex="-1" class="text-page-title page-header__title">
          <span :class="{ 'page-header__mono': monoTitle }">{{ title }}</span>
          <slot name="tag" />
        </h1>
        <p
          v-if="description !== undefined"
          class="page-header__description text-on-surface-variant"
        >
          {{ description }}
        </p>
        <slot name="description" />
      </div>
      <PageActions
        v-if="actions !== undefined"
        :actions="actions"
        :primary-id="primaryActionId"
        @action="emit('action', $event)"
      />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  margin-bottom: 16px;
}
.page-header__row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}
.page-header__main {
  min-width: 0;
}
.page-header__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin: 0;
}
.page-header__title:focus-visible {
  outline-offset: 4px;
}
.page-header__mono {
  font-family: var(--font-mono);
  overflow-wrap: anywhere;
}
.page-header__description {
  margin: 2px 0 0;
  max-width: 70ch;
}
</style>

<script setup lang="ts">
// サイドバー下端の外部リンク領域(DS 5.1・AF-20): OpenSearch Dashboards が設定されているときだけ表示する。
// URL が `null`(未設定・EP-14 の失敗を含む)なら、領域ごと出さない。`target="_blank" rel="noopener"` と、視覚的に隠した
// 「(別タブで開く)」を添える。`featureFlag` の評価はナビ(SideNav・ここ)だけ(E 4.5)。
import { computed } from 'vue'

import { useDashboardsUrl } from '@/admin/queries/meta'
import { mdiOpenInNew } from '@/shared/theme/icons'

import { externalLinks, toSafeExternalUrl } from './externalLinks'

const dashboardsUrl = useDashboardsUrl()

const links = computed(() => {
  const urls = { dashboards: toSafeExternalUrl(dashboardsUrl.value) }
  return externalLinks.flatMap((definition) => {
    const href = urls[definition.source]
    return href === null ? [] : [{ ...definition, href }]
  })
})
</script>

<template>
  <ul v-if="links.length > 0" class="external-links" aria-label="外部リンク">
    <li v-for="link in links" :key="link.id">
      <a class="external-links__item" :href="link.href" target="_blank" rel="noopener">
        <v-icon :icon="link.icon" size="20" />
        <span>{{ link.label }}</span>
        <v-icon :icon="mdiOpenInNew" size="16" class="external-links__external" />
        <span class="sr-only">(別タブで開く)</span>
      </a>
    </li>
  </ul>
</template>

<style scoped>
.external-links {
  list-style: none;
  margin: 0;
  padding: 0;
}
.external-links__item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
  padding: 0 12px;
  border-radius: 4px;
  color: rgb(var(--v-theme-on-surface));
  text-decoration: none;
}
.external-links__item:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}
.external-links__external {
  margin-left: auto;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>

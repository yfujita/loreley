<script setup lang="ts">
// パンくず(DS 5.2): 2 階層以上の画面だけに出す。末尾は現在のページ(リンクにせず `aria-current="page"`)。
// 項目は `useBreadcrumbs` が組み立てて `PageHeader` に渡す。ここは描くだけ。
// `VBreadcrumbs` は使わない: 末尾(disabled)に `aria-current` を付けず、区切りのアイコンも自前で描く必要があるため(FMOD-U-10)。
import { mdiChevronRight } from '@/shared/theme/icons'
import type { BreadcrumbItem } from '@/admin/lib/injectionKeys'

defineProps<{ items: readonly BreadcrumbItem[] }>()
</script>

<template>
  <nav v-if="items.length > 0" class="page-breadcrumbs" aria-label="パンくず">
    <ol>
      <li v-for="(item, index) in items" :key="index">
        <router-link v-if="item.to !== null" :to="item.to">{{ item.title }}</router-link>
        <span
          v-else
          class="page-breadcrumbs__current text-on-surface-variant"
          aria-current="page"
          >{{ item.title }}</span
        >
        <v-icon
          v-if="index < items.length - 1"
          class="page-breadcrumbs__divider"
          :icon="mdiChevronRight"
          size="16"
          aria-hidden="true"
        />
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.page-breadcrumbs {
  margin-bottom: 4px;
}
.page-breadcrumbs ol {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.page-breadcrumbs li {
  display: flex;
  align-items: center;
  gap: 4px;
}
.page-breadcrumbs a {
  text-decoration: none;
  /* 操作領域の高さを 24px 以上にする(DS 2.3) */
  padding: 3px 0;
}
.page-breadcrumbs a:hover {
  text-decoration: underline;
}
.page-breadcrumbs__divider {
  color: rgb(var(--v-theme-on-surface-variant));
}
.page-breadcrumbs__current {
  overflow-wrap: anywhere;
}
</style>

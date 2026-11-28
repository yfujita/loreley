<script setup lang="ts">
// コンポーネントタイル(DS 4.16。D1): 白面・境界線・角丸 8px。1 行目に名前(等幅)とステータスタグ、
// 2 行目に役割、3 行目以降に確認の補足、末尾に導線のリンク。
// 異常は左に 4px の `error` の帯と枠、判定不能は `warning` の帯と枠、未設定は点線の枠と薄い面。
// 状態は色だけに頼らず、タグの形と文言でも示す(帯は補助)。タイルは操作要素ではないので、ホバーで変化しない。
import StatusTag from '@/shared/ui/StatusTag.vue'

import type { ComponentTileModel } from './types'

defineProps<{ model: ComponentTileModel }>()
</script>

<template>
  <li
    class="component-tile"
    :class="`component-tile--${model.status}`"
    :data-testid="`d1-tile-${model.id}`"
  >
    <div class="component-tile__head">
      <h3 class="text-tile-name">{{ model.id }}</h3>
      <StatusTag kind="health" :value="model.status" />
    </div>
    <p class="text-caption-sm text-on-surface-variant">{{ model.role }}</p>
    <p
      class="component-tile__detail text-caption-sm"
      :class="{ 'text-on-surface-variant': !model.emphasized }"
    >
      {{ model.detail }}
    </p>
    <p v-if="model.link !== null" class="component-tile__link text-caption-sm">
      <router-link :to="{ name: model.link.routeName }">{{ model.link.label }}</router-link>
    </p>
  </li>
</template>

<style scoped>
.component-tile {
  display: grid;
  gap: 4px;
  align-content: start;
  min-width: 0;
  padding: 14px 16px 12px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
.component-tile p,
.component-tile h3 {
  margin: 0;
}
.component-tile__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.component-tile__detail {
  margin-top: 4px;
}
.component-tile__link {
  margin-top: 4px;
}
/* リンクの操作領域は高さ 24px 以上(WCAG 2.5.8。dashboard 8 章) */
.component-tile__link a {
  display: inline-block;
  padding: 3px 0;
}
.component-tile--abnormal {
  border-color: rgb(var(--v-theme-error));
  border-left-width: 4px;
  padding-left: 13px;
}
.component-tile--undetermined {
  border-color: rgb(var(--v-theme-warning));
  border-left-width: 4px;
  padding-left: 13px;
}
.component-tile--not_configured {
  background: rgba(var(--v-theme-surface-variant), 0.5);
  border-style: dashed;
  border-color: rgb(var(--v-theme-line-strong));
}
</style>

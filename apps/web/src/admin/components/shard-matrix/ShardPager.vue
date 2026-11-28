<script setup lang="ts">
// ページ送り(DS 4.15・opensearch 3.4): 「前へ」「ページ選択」「次へ」。マトリクスの列だけを切り替える。
// 端のボタンは `aria-disabled="true"`(`disabled` にしない。押した直後に無効になってもフォーカスを失わないため)。
// `VBtn` は `aria-disabled` を透過するがクリックは発火するので、ハンドラの先頭でも端のページを判定する。
import { computed, useId } from 'vue'

import { mdiChevronLeft, mdiChevronRight } from '@/shared/theme/icons'

const props = defineProps<{
  /** 1 起点 */
  page: number
  pageCount: number
}>()

const emit = defineEmits<{ 'update:page': [page: number] }>()

const selectId = useId()
const isFirst = computed(() => props.page <= 1)
const isLast = computed(() => props.page >= props.pageCount)
const pages = computed(() => Array.from({ length: props.pageCount }, (_, i) => i + 1))

// 端のページでは何もしない(`aria-disabled` のボタンもクリックは発火するため。`go(0)`・`go(pageCount + 1)` は範囲外で止まる)。
function go(page: number): void {
  if (page < 1 || page > props.pageCount || page === props.page) return
  emit('update:page', page)
}

function onSelect(event: Event): void {
  go(Number((event.target as HTMLSelectElement).value))
}
</script>

<template>
  <div class="shard-pager" role="group" aria-label="シャードの配置のページ送り">
    <v-btn
      variant="outlined"
      size="small"
      type="button"
      :prepend-icon="mdiChevronLeft"
      aria-label="前へ。シャードの配置の前のページ"
      :aria-disabled="isFirst"
      @click="go(page - 1)"
    >
      前へ
    </v-btn>
    <div class="shard-pager__select">
      <label :for="selectId">ページ</label>
      <select :id="selectId" :value="page" @change="onSelect">
        <option v-for="n in pages" :key="n" :value="n">{{ n }} / {{ pageCount }}</option>
      </select>
    </div>
    <v-btn
      variant="outlined"
      size="small"
      type="button"
      :append-icon="mdiChevronRight"
      aria-label="次へ。シャードの配置の次のページ"
      :aria-disabled="isLast"
      @click="go(page + 1)"
    >
      次へ
    </v-btn>
  </div>
</template>

<style scoped>
.shard-pager {
  display: flex;
  align-items: center;
  gap: 8px;
}
.shard-pager__select {
  display: flex;
  align-items: center;
  gap: 8px;
}
.shard-pager select {
  height: 32px;
  width: 96px;
  padding: 0 8px;
  border: 1px solid rgb(var(--v-theme-line-strong));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
}
/* 幅 600px 未満: 3 つの部品を 320px で 1 行に収める(各 44px。余白・間隔・選択の幅を詰める。ラベルは視覚的に隠す) */
@media (max-width: 599px) {
  .shard-pager {
    flex-wrap: nowrap;
    gap: 6px;
  }
  .shard-pager select {
    height: 44px;
    width: 84px;
  }
  .shard-pager__select label {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
  .shard-pager :deep(.v-btn) {
    padding: 0 10px;
  }
}
</style>

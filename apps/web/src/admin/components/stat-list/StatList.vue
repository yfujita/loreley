<script setup lang="ts">
// 件数ブロック(DS 4.10): 複数の件数を横に並べる `<dl>`。項目名(12px・on-surface-variant)の下に値(20px / 600・等幅数字)。
// 補足(「新規 2 · 更新 12」)は値の下。件数が 0 でも「0」を出す(空欄にしない)。値が取得できない(null)ときは「—」。
// 値が他画面の一覧へつながる件数(スキップ・原本サイズ超過・エラー)は、`to` を渡すと値がリンクになる。
// 幅 1145px 以上は 5 列、840〜1144px は 3 列、840px 未満は 2 列に折り返す。
import { formatCountOrDash } from '@/shared/lib/number'

export type StatItem = {
  key: string
  label: string
  /** null は取得できない(「—」) */
  value: number | null
  note?: string
  /** 値をリンクにする(`router-link` の `to`) */
  to?: string | { name: string; params?: Record<string, string>; query?: Record<string, string> }
}

defineProps<{ items: readonly StatItem[] }>()
</script>

<template>
  <dl class="stat-list">
    <div v-for="item in items" :key="item.key" class="stat-list__item">
      <dt class="text-caption-sm text-on-surface-variant">{{ item.label }}</dt>
      <dd class="text-stat-value">
        <router-link v-if="item.to !== undefined" :to="item.to">{{
          formatCountOrDash(item.value)
        }}</router-link>
        <template v-else>{{ formatCountOrDash(item.value) }}</template>
        <span v-if="item.value === null" class="sr-only">(取得できません)</span>
      </dd>
      <dd v-if="item.note !== undefined" class="text-caption-sm text-on-surface-variant">
        {{ item.note }}
      </dd>
    </div>
  </dl>
</template>

<style scoped>
.stat-list {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
  margin: 0;
}
.stat-list__item dt,
.stat-list__item dd {
  margin: 0;
}
@media (max-width: 1144px) {
  .stat-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 839px) {
  .stat-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>

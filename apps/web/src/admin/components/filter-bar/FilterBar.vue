<script setup lang="ts">
// 絞り込みバー(DS 4.12): 一覧の上に置く、セレクト(ラベルは上・高さ 36px)を横に並べた帯。
// 条件は一覧の件数・ページングと一緒に URL のクエリに持たせ(画面が `useListParams` で扱う)、再読み込みや
// 他画面からのリンクで再現できるようにする。ここは見せ方だけで、値は props で受け、変更を `change` で通知する。
// 絞り込みの結果が 0 件のときの「条件に合う…がありません」と「条件を解除」は、画面の状態ブロックが出す。
import { useId } from 'vue'

export type FilterOption = { title: string; value: string }

export type FilterField = {
  key: string
  label: string
  /** 「すべて」も、画面が選択肢として渡す(値は空文字などにする) */
  options: readonly FilterOption[]
  value: string
  /** `data-testid`(DS 9。例 `j1-filter-source`) */
  testid?: string
}

defineProps<{
  fields: readonly FilterField[]
  /** 「条件を解除」を出す(条件が 1 つでも既定と違うとき) */
  showReset?: boolean
}>()

const emit = defineEmits<{
  change: [key: string, value: string]
  reset: []
}>()

const idBase = useId()
</script>

<template>
  <form class="filter-bar" aria-label="絞り込み" @submit.prevent>
    <div v-for="field in fields" :key="field.key" class="filter-bar__field">
      <label :for="`${idBase}-${field.key}`" class="text-body-strong">{{ field.label }}</label>
      <v-select
        :id="`${idBase}-${field.key}`"
        class="filter-bar__select"
        density="compact"
        item-title="title"
        item-value="value"
        :items="field.options as FilterOption[]"
        :model-value="field.value"
        :data-testid="field.testid"
        @update:model-value="emit('change', field.key, String($event))"
      />
    </div>
    <v-btn v-if="showReset" variant="text" size="small" @click="emit('reset')">条件を解除</v-btn>
  </form>
</template>

<style scoped>
/* セレクトの高さは 36px(DS 4.12。入力欄の 40px より低い)。幅 600px 未満は 44px(DS 2.3) */
.filter-bar__select :deep(.v-field) {
  --v-input-control-height: 36px;
  --v-field-padding-bottom: 4px;
}
@media (max-width: 599px) {
  .filter-bar__select :deep(.v-field) {
    --v-input-control-height: 44px;
    --v-field-padding-bottom: 10px;
  }
}
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.filter-bar__field {
  display: grid;
  gap: 4px;
  min-width: 190px;
}
</style>

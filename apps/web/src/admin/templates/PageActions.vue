<script setup lang="ts">
// ページ見出しの操作(DS 4.13)。`ActionSpec[]`(状態 → 操作の表が返す)を描く。
// - `visible` が false の操作は出さない(実行の見込みがない)
// - `disabledReason` がある操作は、無効にして理由を近くに出し、`aria-describedby` で結ぶ(状況が変われば実行できる)
// - 主操作は 1 つ(primary)。`primaryId` で指す。それ以外は outlined(副次)
// 操作の実行は `action` イベントで id を渡す(ダイアログを開くのは画面)。
import { computed, useId } from 'vue'

import type { ActionSpec } from '@/admin/lib/actions'

const props = defineProps<{
  actions: readonly ActionSpec[]
  /** 主操作の `ActionSpec.id`。省略すると、すべて副次の見た目 */
  primaryId?: string | null
}>()

const emit = defineEmits<{ action: [id: string] }>()

const idBase = useId()
const visibleActions = computed(() => props.actions.filter((action) => action.visible))

function reasonId(action: ActionSpec): string {
  return `${idBase}-${action.id}-reason`
}
</script>

<template>
  <div v-if="visibleActions.length > 0" class="page-actions">
    <div v-for="action in visibleActions" :key="action.id" class="page-actions__item">
      <v-btn
        :variant="action.id === primaryId ? 'flat' : 'outlined'"
        :color="action.id === primaryId ? 'primary' : undefined"
        :disabled="action.disabledReason !== null"
        :aria-describedby="action.disabledReason !== null ? reasonId(action) : undefined"
        @click="emit('action', action.id)"
      >
        {{ action.label }}
      </v-btn>
      <p
        v-if="action.disabledReason !== null"
        :id="reasonId(action)"
        class="page-actions__reason text-caption-sm text-on-surface-variant"
      >
        {{ action.disabledReason }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.page-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.page-actions__item {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.page-actions__reason {
  margin: 0;
  max-width: 28ch;
  text-align: right;
}
</style>

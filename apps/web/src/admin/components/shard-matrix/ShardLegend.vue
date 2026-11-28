<script setup lang="ts">
// 凡例(DS 4.15・opensearch 3.3): チップの実物+説明。プライマリ・レプリカは常に、それ以外(未割り当てのレプリカ・
// 未割り当てのプライマリ・初期化中/移動中)は、表示対象のデータにあるときだけ出す(ページを送っても変わらない)。
import { computed } from 'vue'

import ShardChip from './ShardChip.vue'
import type { MatrixLegend, ShardChipModel } from './types'

const props = defineProps<{ legend: MatrixLegend }>()

type LegendItem = { key: string; chip: ShardChipModel; label: string }

const sample = (role: string, state: string): ShardChipModel => ({ number: 0, role, state })

const items = computed<LegendItem[]>(() => {
  const list: LegendItem[] = [
    { key: 'primary', chip: sample('primary', 'started'), label: 'プライマリ' },
    { key: 'replica', chip: sample('replica', 'started'), label: 'レプリカ' },
  ]
  if (props.legend.unassignedReplica) {
    list.push({
      key: 'unassigned-replica',
      chip: sample('replica', 'unassigned'),
      label: '未割り当てのレプリカ(点線)',
    })
  }
  if (props.legend.unassignedPrimary) {
    list.push({
      key: 'unassigned-primary',
      chip: sample('primary', 'unassigned'),
      label: '未割り当てのプライマリ(点線・赤)',
    })
  }
  if (props.legend.inTransit) {
    list.push({
      key: 'in-transit',
      chip: sample('primary', 'relocating'),
      label: '初期化中・移動中',
    })
  }
  return list
})
</script>

<template>
  <ul class="shard-legend" aria-label="凡例">
    <li v-for="item in items" :key="item.key">
      <ShardChip :chip="item.chip" :readout="false" />
      <span>{{ item.label }}</span>
    </li>
  </ul>
</template>

<style scoped>
.shard-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  align-items: center;
  margin: 0;
  padding: 12px 16px;
  list-style: none;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.shard-legend li {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
@media (max-width: 599px) {
  .shard-legend {
    padding: 12px;
  }
}
</style>

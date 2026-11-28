<script setup lang="ts">
// 概況(DS 4.15・opensearch 3.0): カード「クラスタ状態」の上部の領域。クラスタ名・状態タグ・状態の説明・件数 4 項目
// (ノード / アクティブ(うち移動中)/ 未割り当て / 初期化中)。件数ブロック(DS 4.10)を、カード内用に小さくした形。
// **アクティブ + 初期化中 + 未割り当て = 全シャード数**(移動中はアクティブの内数なので足さない)。
// クラスタ全体の値で、絞り込みの対象外。取得は 1 回の結果(概況だけ・マトリクスだけが失敗する状態はない)。
import { computed } from 'vue'

import type { ClusterSummary } from '@/admin/api'
import { toClusterStatus, type ClusterStatus } from '@/admin/lib/clusterValues'
import { formatCount } from '@/shared/lib/number'
import StatusTag from '@/shared/ui/StatusTag.vue'

const props = defineProps<{
  cluster: ClusterSummary
  /** 再取得に失敗して前回の値を出している。状態の説明に「前回取得時の値です。」を添える */
  stale: boolean
}>()

// 状態の説明(opensearch 3.1)。未知の値は、タグ(中立表示)だけで説明を出さない。
const DESCRIPTIONS: Record<ClusterStatus, string> = {
  green: 'すべてのシャードが割り当てられています。',
  yellow:
    'プライマリシャードはすべて割り当てられていますが、一部のレプリカシャードが割り当てられていません。単一ノードでレプリカが 1 以上のインデックスは、通常 yellow になります。',
  red: '一部のプライマリシャードが割り当てられていません。該当するインデックスの検索や登録に影響する可能性があります。',
}

const description = computed(() => {
  const status = toClusterStatus(props.cluster.status)
  const text = status === null ? '' : DESCRIPTIONS[status]
  return props.stale ? `${text} 前回取得時の値です。`.trim() : text
})

const stats = computed(() => [
  { key: 'nodes', label: 'ノード', value: props.cluster.node_count, note: null },
  {
    key: 'active',
    label: 'アクティブ',
    value: props.cluster.active_shards,
    note: `うち移動中 ${formatCount(props.cluster.relocating_shards)}`,
  },
  { key: 'unassigned', label: '未割り当て', value: props.cluster.unassigned_shards, note: null },
  { key: 'initializing', label: '初期化中', value: props.cluster.initializing_shards, note: null },
])
</script>

<template>
  <div class="cluster-summary" data-testid="o1-summary">
    <dl class="cluster-summary__head">
      <div>
        <dt class="text-caption-sm text-on-surface-variant">クラスタ名</dt>
        <dd class="text-id">{{ cluster.name }}</dd>
      </div>
      <div>
        <dt class="text-caption-sm text-on-surface-variant">状態</dt>
        <dd><StatusTag kind="cluster" :value="cluster.status" /></dd>
      </div>
    </dl>
    <p v-if="description !== ''" class="cluster-summary__description text-on-surface-variant">
      {{ description }}
    </p>
    <dl class="cluster-summary__stats">
      <div v-for="stat in stats" :key="stat.key">
        <dt class="text-caption-sm text-on-surface-variant">{{ stat.label }}</dt>
        <dd class="cluster-summary__value num">
          {{ formatCount(stat.value) }}
          <span v-if="stat.note !== null" class="text-caption-sm text-on-surface-variant">{{
            stat.note
          }}</span>
        </dd>
      </div>
    </dl>
  </div>
</template>

<style scoped>
.cluster-summary {
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.cluster-summary dl,
.cluster-summary dd,
.cluster-summary p {
  margin: 0;
}
.cluster-summary__head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px 32px;
  padding: 12px 16px 0;
}
.cluster-summary__head > div {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.cluster-summary__head dd {
  overflow-wrap: anywhere;
}
.cluster-summary__description {
  max-width: 90ch;
  padding: 6px 16px 12px;
}
.cluster-summary__stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border-top: 1px solid rgba(var(--v-border-color), 0.08);
}
.cluster-summary__stats > div {
  padding: 8px 16px;
  display: grid;
  gap: 2px;
  border-right: 1px solid rgba(var(--v-border-color), 0.08);
}
.cluster-summary__stats > div:last-child {
  border-right: 0;
}
/* 値 18px / 600、「うち移動中 n」は 12px の補足を値の右に同じ行で(DS 4.15) */
.cluster-summary__value {
  font-size: 1.125rem;
  line-height: 1.5;
  font-weight: 600;
}
.cluster-summary__value .text-caption-sm {
  margin-left: 6px;
  font-weight: 400;
}
@media (max-width: 839px) {
  .cluster-summary__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .cluster-summary__stats > div {
    border-bottom: 1px solid rgba(var(--v-border-color), 0.08);
  }
  .cluster-summary__stats > div:nth-child(2n) {
    border-right: 0;
  }
}
</style>

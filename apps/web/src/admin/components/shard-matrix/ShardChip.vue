<script setup lang="ts">
// シャードのチップ(DS 4.15・opensearch 3.3): `P0`(プライマリ)・`R0`(レプリカ)+シャード番号。高さ 24px・等幅・12px / 600。
// 状態は色・枠の線種・アイコン・文字で区別する。色や枠線の濃さには依存しない(枠線の 3:1 は満たさない)。
// 初期化中と移動中は見た目を同一にし、読み上げ(視覚的に隠した文)だけ分ける。
// 未知の役割・状態は中立の見た目にして、値をそのまま読み上げに出す。
import { computed } from 'vue'

import { classifyShard, toShardRole, type ShardChipKind } from '@/admin/lib/clusterValues'
import { mdiAlertOutline, mdiCloseOctagonOutline, mdiSwapHorizontal } from '@/shared/theme/icons'

import type { ShardChipModel } from './types'

const props = withDefaults(
  defineProps<{
    chip: ShardChipModel
    /** 視覚的に隠した状態の読み上げを付ける。凡例の見本には付けない(説明の文と重複するため) */
    readout?: boolean
  }>(),
  { readout: true },
)

const ICONS: Partial<Record<ShardChipKind, string>> = {
  'unassigned-primary': mdiCloseOctagonOutline,
  'unassigned-replica': mdiAlertOutline,
  initializing: mdiSwapHorizontal,
  relocating: mdiSwapHorizontal,
}
const STATE_READOUTS: Partial<Record<ShardChipKind, string>> = {
  primary: '割り当て済み',
  replica: '割り当て済み',
  'unassigned-primary': '未割り当て',
  'unassigned-replica': '未割り当て',
  initializing: '初期化中',
  relocating: '移動中',
}

const kind = computed(() => classifyShard(props.chip.role, props.chip.state))
const icon = computed(() => ICONS[kind.value])

const letter = computed(() => {
  const role = toShardRole(props.chip.role)
  if (role === null) return '?'
  return role === 'primary' ? 'P' : 'R'
})
const roleLabel = computed(() => {
  const role = toShardRole(props.chip.role)
  if (role === null) return props.chip.role
  return role === 'primary' ? 'プライマリ' : 'レプリカ'
})
const readoutText = computed(() => {
  const state = STATE_READOUTS[kind.value] ?? props.chip.state
  return `(${roleLabel.value}。${state})`
})
</script>

<template>
  <span class="shard-chip" :class="`shard-chip--${kind}`">
    <v-icon v-if="icon !== undefined" class="shard-chip__icon" :icon="icon" size="14" />
    {{ letter }}{{ chip.number }}
    <span v-if="readout" class="sr-only">{{ readoutText }}</span>
  </span>
</template>

<style scoped>
.shard-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 24px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
}
/* プライマリ(割り当て済み): primary-container 面・実線 */
.shard-chip--primary {
  background: rgb(var(--v-theme-primary-container));
  color: rgb(var(--v-theme-on-primary-container));
  border-color: rgba(var(--v-theme-primary), 0.45);
}
/* レプリカ(割り当て済み): 白面・line-strong の実線 */
.shard-chip--replica {
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  border-color: rgb(var(--v-theme-line-strong));
}
/* 未割り当て: 点線(warning・error)+アイコン */
.shard-chip--unassigned-replica {
  background: rgb(var(--v-theme-warning-container));
  color: rgb(var(--v-theme-on-warning-container));
  border: 1px dashed rgb(var(--v-theme-warning));
}
.shard-chip--unassigned-primary {
  background: rgb(var(--v-theme-error-container));
  color: rgb(var(--v-theme-on-error-container));
  border: 1px dashed rgb(var(--v-theme-error));
}
/* 初期化中・移動中: info-container 面・実線+矢印アイコン */
.shard-chip--initializing,
.shard-chip--relocating {
  background: rgb(var(--v-theme-info-container));
  color: rgb(var(--v-theme-on-info-container));
  border-color: rgba(var(--v-theme-info), 0.5);
}
/* 未知の値: 中立(secondary-container 面・実線) */
.shard-chip--unknown {
  background: rgb(var(--v-theme-secondary-container));
  color: rgb(var(--v-theme-on-secondary-container));
  border-color: rgb(var(--v-theme-line-strong));
}
</style>

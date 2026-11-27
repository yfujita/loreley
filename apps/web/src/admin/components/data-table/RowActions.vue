<script setup lang="ts">
// 表の行の操作(DS 4.3): 主操作 1 つ(tonal ボタン)+その他の操作(`⋮` のメニュー。危険な操作は下段・赤字・区切り線の下)。
// 操作の表(`ActionSpec[]`)は画面ごとの `*Actions.ts` が返す。実行は `action` イベントで id を渡す(ダイアログを開くのは画面)。
// 行の主操作ボタンの名前には対象の識別子を含める(視覚的に隠した「(識別子)」。DS 4.3・8)。
import { computed, useId } from 'vue'

import type { ActionSpec } from '@/admin/lib/actions'
import { mdiDotsVertical } from '@/shared/theme/icons'

const props = defineProps<{
  actions: readonly ActionSpec[]
  /** 行の対象の識別子(`source_id`・ジョブ ID)。アクセシブルネームに含める */
  target: string
  /** 主操作の `ActionSpec.id` */
  primaryId?: string | null
  /** 主操作をアイコンのみにする(表のカード幅が 720px 未満のとき。DS 4.3)。ツールチップで操作名を出す */
  iconOnly?: boolean
  /** `iconOnly` のときに描くアイコン(SVG パス)。ないときは文言のまま */
  primaryIcon?: string
}>()

const emit = defineEmits<{ action: [id: string] }>()

const reasonId = `${useId()}-reason`

const visibleActions = computed(() => props.actions.filter((action) => action.visible))
const primary = computed(() => visibleActions.value.find((action) => action.id === props.primaryId))
const menuActions = computed(() => {
  const others = visibleActions.value.filter((action) => action.id !== props.primaryId)
  // 危険な操作(要入力確認)は下段にまとめる。
  return [
    ...others.filter((action) => action.level !== 'confirm-typed'),
    ...others.filter((action) => action.level === 'confirm-typed'),
  ]
})
const firstDangerIndex = computed(() =>
  menuActions.value.findIndex((action) => action.level === 'confirm-typed'),
)
const showIconOnly = computed(() => props.iconOnly === true && props.primaryIcon !== undefined)
</script>

<template>
  <div class="row-actions">
    <v-btn
      v-if="primary"
      size="small"
      color="primary-container"
      :disabled="primary.disabledReason !== null"
      :icon="showIconOnly ? primaryIcon : undefined"
      :aria-label="showIconOnly ? `${primary.label}(${target})` : undefined"
      :title="showIconOnly ? primary.label : (primary.disabledReason ?? undefined)"
      :aria-describedby="primary.disabledReason !== null ? reasonId : undefined"
      @click="emit('action', primary.id)"
    >
      <template v-if="!showIconOnly">
        {{ primary.label }}<span class="sr-only">({{ target }})</span>
      </template>
    </v-btn>
    <!-- 無効のボタンは pointer-events:none で title が届かず、キーボードにも届かない。理由を、視覚的に隠した文言として結ぶ(DS 4.8・8)。
         行に理由を出すと表の密度を落とすので、視覚的には出さない -->
    <span v-if="primary?.disabledReason" :id="reasonId" class="sr-only">{{
      primary.disabledReason
    }}</span>
    <v-menu v-if="menuActions.length > 0">
      <template #activator="{ props: menuProps }">
        <v-btn
          v-bind="menuProps"
          icon
          size="small"
          variant="text"
          color="on-surface"
          :aria-label="`その他の操作(${target})`"
        >
          <v-icon :icon="mdiDotsVertical" />
        </v-btn>
      </template>
      <v-list>
        <template v-for="(action, index) in menuActions" :key="action.id">
          <v-divider v-if="index === firstDangerIndex && index > 0" />
          <v-list-item
            :title="action.label"
            :subtitle="action.disabledReason ?? undefined"
            :disabled="action.disabledReason !== null"
            :class="{ 'row-actions__danger': action.level === 'confirm-typed' }"
            @click="emit('action', action.id)"
          />
        </template>
      </v-list>
    </v-menu>
  </div>
</template>

<style scoped>
.row-actions {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}
.row-actions__danger :deep(.v-list-item-title) {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}
</style>

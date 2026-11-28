<script setup lang="ts">
// 確認ダイアログ(DS 4.8): 危険度の水準(要確認・標準 / 警告つき / 要入力確認)に応じて、帯・実行ボタンの色・閉じ方・初期フォーカスが決まる。
// 本体(対象・結果の説明・警告枠・確認チェック・入力欄・ダイアログ内アラート)は default スロットで受ける。
//
// - 共通: `role="dialog"`・`aria-modal`(`VDialog` が付ける)・`aria-labelledby`(見出し)。フォーカスはダイアログ内に閉じ込め、
//   閉じたら開く直前にフォーカスがあった要素へ戻す。Esc で閉じる(警告つき・要入力確認は `persistent`: Esc・背面クリックでは閉じない)
// - 初期フォーカス: 要確認・標準は見出し(`tabindex="-1"`)、警告つきは最初の入力要素(なければ見出し)、要入力確認は入力欄
// - 無効の実行ボタンには、必ず理由の文言を実行ボタンの下に出し、`aria-describedby` で結ぶ
// - 実行中(`pending`)は実行ボタン・キャンセルを無効にし(二重送信を防ぐ)、閉じない(結果のアラートを見逃さないため)
import { computed, nextTick, ref, useId, watch } from 'vue'

import { resolveDialogAppearance, type DialogLevel, type Severity } from './dialogLevel'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    level: DialogLevel
    /** 含まれる指定の重さ(警告つきの帯・実行ボタンの色を、最も重い指定に合わせる) */
    severities?: readonly Severity[]
    /** 見出し(動詞+対象。「データソース「x」を削除」など) */
    title: string
    /** 実行ボタンの文言(見出しと同じ動詞) */
    executeLabel: string
    cancelLabel?: string
    /** 実行できない理由。あれば実行ボタンを無効にして、理由を実行ボタンの下に出す */
    disabledReason?: string | null
    /** 実行中 */
    pending?: boolean
    /** 実行ボタンを出さず「閉じる」だけにする(結果の確認後など) */
    hideExecute?: boolean
    /** `data-testid`(DS 9。`dlg-{目的}`)。`role="dialog"` の要素に付く */
    testid?: string
  }>(),
  {
    severities: () => [],
    cancelLabel: 'キャンセル',
    disabledReason: null,
    pending: false,
    hideExecute: false,
    testid: undefined,
  },
)

const emit = defineEmits<{
  'update:modelValue': [open: boolean]
  execute: []
  cancel: []
}>()

const idBase = useId()
const titleId = `${idBase}-title`
const reasonId = `${idBase}-reason`
const heading = ref<HTMLElement | null>(null)
const body = ref<HTMLElement | null>(null)

const appearance = computed(() => resolveDialogAppearance(props.level, props.severities))
// 実行中は閉じない(失敗のアラートを見逃さない。結果不明のときに実行の有無を誤解しない)。
const persistent = computed(() => appearance.value.persistent || props.pending)
const executeDisabled = computed(() => props.pending || props.disabledReason !== null)

// 閉じたら、開く直前にフォーカスがあった要素へ戻す(DS 4.8)。DOM から外れた要素(メニューの項目から開いた場合など)へは
// 戻さない。その場合の戻り先は、行の操作を持つ画面のフェーズで決める(FMOD-U-5)。
let opener: HTMLElement | null = null
watch(
  () => props.modelValue,
  async (open, wasOpen) => {
    if (open && !wasOpen) {
      opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
      return
    }
    if (!open && wasOpen) {
      const target = opener
      opener = null
      await nextTick()
      if (target?.isConnected === true) target.focus({ preventScroll: true })
    }
  },
  { flush: 'sync' },
)

/** 開いた後の初期フォーカス(DS 4.8)。 */
function focusInitial(): void {
  const firstInput =
    props.level === 'confirm'
      ? null
      : body.value?.querySelector<HTMLElement>(
          'input:not([disabled]), select:not([disabled]), textarea:not([disabled])',
        )
  ;(firstInput ?? heading.value)?.focus({ preventScroll: true })
}

function close(): void {
  emit('update:modelValue', false)
  emit('cancel')
}
function onUpdate(open: boolean): void {
  // Esc・背面クリック(persistent でないときだけ届く)
  if (!open) close()
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    :persistent="persistent"
    :aria-labelledby="titleId"
    :data-testid="testid"
    @update:model-value="onUpdate"
    @after-enter="focusInitial"
  >
    <v-card
      class="confirm-dialog"
      :class="appearance.band !== null ? `confirm-dialog--${appearance.band}` : undefined"
    >
      <div v-if="appearance.band !== null" class="confirm-dialog__band" />
      <div class="confirm-dialog__header">
        <h2 :id="titleId" ref="heading" tabindex="-1" class="text-section-title">{{ title }}</h2>
      </div>
      <div ref="body" class="confirm-dialog__body">
        <slot />
      </div>
      <div class="confirm-dialog__actions">
        <v-btn variant="text" :disabled="pending" @click="close">{{ cancelLabel }}</v-btn>
        <v-btn
          v-if="!hideExecute"
          :color="appearance.executeColor"
          :disabled="executeDisabled"
          :aria-describedby="disabledReason !== null ? reasonId : undefined"
          @click="emit('execute')"
          >{{ executeLabel }}</v-btn
        >
        <p
          v-if="!hideExecute && disabledReason !== null"
          :id="reasonId"
          class="confirm-dialog__reason text-caption-sm text-on-surface-variant"
        >
          {{ disabledReason }}
        </p>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.confirm-dialog {
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(26, 37, 48, 0.2);
}
.confirm-dialog__band {
  height: 4px;
}
.confirm-dialog--error .confirm-dialog__band {
  background: rgb(var(--v-theme-error));
}
.confirm-dialog--warning .confirm-dialog__band {
  background: rgb(var(--v-theme-warning));
}
.confirm-dialog__header {
  padding: 20px 24px 8px;
}
.confirm-dialog__header h2 {
  margin: 0;
  overflow-wrap: anywhere;
}
.confirm-dialog__header h2:focus-visible {
  outline-offset: 4px;
}
.confirm-dialog__body {
  display: grid;
  gap: 12px;
  padding: 4px 24px 16px;
  min-width: 0;
  overflow-wrap: anywhere;
}
.confirm-dialog__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 24px 20px;
}
.confirm-dialog__reason {
  flex: 1 1 100%;
  margin: 0;
  text-align: right;
}
@media (max-width: 599px) {
  .confirm-dialog__actions :deep(.v-btn) {
    white-space: normal;
    height: auto;
    min-height: 44px;
    padding-top: 6px;
    padding-bottom: 6px;
  }
}
</style>

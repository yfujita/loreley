<script setup lang="ts">
// 絞り込みフォーム(DS 4.15・opensearch 3.5): 概況の下・マトリクスの上。インデックス名(部分一致)と 状態(複数選択)。
// 即時に絞り込む(名前は 250ms の debounce、Enter ですぐ。「絞り込む」ボタンなし)。IME の変換中は適用せず、確定後に適用する。
// 「条件を解除」は全条件を外し、名前の入力欄へフォーカスを移す。条件がないときは `aria-disabled`(押しても何も起きない)。
// 値(`name`・`states`)は URL が正で、ここは見せ方と入力の通知だけを持つ(絞り込みの計算は features/opensearch/models/indexFilter)。
import { computed, ref, useId, useTemplateRef, watch } from 'vue'

import { useDebouncedRef } from '@/admin/composables/useDebouncedRef'
import { CLUSTER_STATUSES, type ClusterStatus } from '@/admin/lib/clusterValues'
import StatusTag from '@/shared/ui/StatusTag.vue'

const NAME_DEBOUNCE_MS = 250

const props = defineProps<{
  /** URL の条件(正規化済みの名前) */
  name: string
  /** URL の条件(3 つとも選んだ表示を保つため、正規化の前) */
  states: readonly ClusterStatus[]
  /** 条件が 1 つ以上ある(3 つとも選んだ状態は条件なし) */
  hasCondition: boolean
  /** 読み込み中は入力できない(位置が動かないよう、無効のまま出す) */
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:name': [value: string]
  'update:states': [value: ClusterStatus[]]
  clear: []
}>()

// 表示順は red → yellow → green(マトリクスの並びと同じ)。
const STATE_OPTIONS = [...CLUSTER_STATUSES].reverse()

const idBase = useId()
const nameInput = useTemplateRef<{ focus: () => void }>('nameInput')

// 入力中の文字(URL とは別)。URL → 入力は、戻る・解除など「自分が通知した値以外」への変更だけを反映する
// (自分の通知が URL に反映されるまでの間に続けて入力しても、入力欄を書き換えない)。
const text = ref(props.name)
let lastEmittedName = props.name

function emitName(value: string): void {
  lastEmittedName = value.trim()
  emit('update:name', value)
}

watch(
  () => props.name,
  (name) => {
    if (name === lastEmittedName) return
    lastEmittedName = name
    text.value = name
  },
)

const debouncedText = useDebouncedRef(text, NAME_DEBOUNCE_MS)
const isComposing = ref(false)
watch(debouncedText, (value) => {
  if (!isComposing.value) emitName(value)
})

function onCompositionEnd(): void {
  isComposing.value = false
  emitName(text.value)
}

// Enter: 待たずにすぐ絞り込む(フォームの送信は止め、ページは移動しない)。
function submit(): void {
  emitName(text.value)
}

function toggleState(status: ClusterStatus, checked: boolean): void {
  const selected = props.states.filter((state) => state !== status)
  emit('update:states', checked ? [...selected, status] : selected)
}

function clear(): void {
  // `aria-disabled` のボタンもクリックは発火する。条件がないときは何もしない(フォーカスも動かさない)。
  if (!props.hasCondition) return
  text.value = ''
  lastEmittedName = ''
  emit('clear')
  nameInput.value?.focus()
}

const nameHelpId = computed(() => `${idBase}-name-help`)
</script>

<template>
  <form
    class="index-filter"
    role="search"
    aria-label="インデックスの絞り込み"
    data-testid="o1-filter"
    novalidate
    @submit.prevent="submit"
  >
    <div class="index-filter__field index-filter__name">
      <label class="index-filter__label" :for="`${idBase}-name`">インデックス名</label>
      <v-text-field
        :id="`${idBase}-name`"
        ref="nameInput"
        v-model="text"
        type="text"
        placeholder="名前の一部(例: logs)"
        autocomplete="off"
        spellcheck="false"
        :aria-describedby="nameHelpId"
        :disabled="disabled"
        @compositionstart="isComposing = true"
        @compositionend="onCompositionEnd"
      />
      <span :id="nameHelpId" class="sr-only">
        大文字小文字は区別しません。入力するとすぐに絞り込みます。
      </span>
    </div>
    <fieldset class="index-filter__field index-filter__states">
      <legend class="index-filter__label">状態(複数選択できます。選ばなければすべて)</legend>
      <div class="index-filter__checks">
        <v-checkbox
          v-for="status in STATE_OPTIONS"
          :key="status"
          class="index-filter__check"
          density="compact"
          color="primary"
          hide-details
          :model-value="states.includes(status)"
          :disabled="disabled"
          @update:model-value="toggleState(status, $event === true)"
        >
          <template #label><StatusTag kind="index" :value="status" /></template>
        </v-checkbox>
      </div>
    </fieldset>
    <v-btn
      class="index-filter__clear"
      variant="text"
      size="small"
      type="button"
      :disabled="disabled"
      :aria-disabled="disabled ? undefined : !hasCondition"
      @click="clear"
    >
      条件を解除
    </v-btn>
  </form>
</template>

<style scoped>
.index-filter {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 8px 24px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.index-filter__field {
  display: grid;
  gap: 4px;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
}
.index-filter__name {
  width: 280px;
  max-width: 100%;
}
/* ラベル 12px / 400(DS 4.15。絞り込みバーの帯に収めるため、4.6 の 14px / 600 ではない) */
.index-filter__label {
  padding: 0;
  font-size: 0.75rem;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface-variant));
}
.index-filter__checks {
  display: flex;
  flex-wrap: wrap;
  gap: 0 16px;
}
/* ラベル全体を押せる。高さ 40px(幅 600px 未満は 44px) */
.index-filter__check {
  --v-input-control-height: 40px;
  flex: none;
}
.index-filter__check :deep(.v-selection-control) {
  min-height: 40px;
}
.index-filter__check :deep(.v-label) {
  opacity: 1;
}
.index-filter__clear {
  align-self: flex-end;
}
@media (max-width: 599px) {
  .index-filter {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    padding: 12px;
  }
  .index-filter__name {
    width: 100%;
  }
  .index-filter__checks {
    gap: 0 12px;
  }
  .index-filter__check :deep(.v-selection-control) {
    min-height: 44px;
  }
  .index-filter__clear {
    align-self: stretch;
  }
}
</style>

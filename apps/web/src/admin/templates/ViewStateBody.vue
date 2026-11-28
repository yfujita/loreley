<script setup lang="ts">
// `viewState`(`features` の composable が `useViewState` で作る)を、スケルトン・エラー・見つかりません・空・
// stale アラートとして描く(E 4.4・6.2。DS 4.5)。4 型のテンプレートが共有する(画面は状態の出し分けを自前で書かない)。
// `templates` は Query・`error.code` を知らない(R7)。`viewState` と文言だけを props で受ける。
import { computed, ref, useSlots, watch } from 'vue'

import type { ViewState } from '@/admin/lib/viewState'
import { formatDate } from '@/shared/lib/datetime'
import { mdiRefresh } from '@/shared/theme/icons'
import PageAlert from '@/shared/ui/PageAlert.vue'
import StateBlock from '@/shared/ui/StateBlock.vue'
import TimeText from '@/shared/ui/TimeText.vue'

import type { StateTexts } from './types'

const props = withDefaults(
  defineProps<{
    viewState: ViewState
    texts?: StateTexts
    /** `data-testid` の接頭辞(DS 9。例 `s1` → `s1-state-empty`) */
    testidPrefix?: string
    /** 見出し・空・エラー・見つかりません・読み込み中のブロックをカードで包む(ページにカードがないとき) */
    card?: boolean
    /** 状態ブロックの見出しのレベル(カード内に `h2` があるとき 3) */
    headingLevel?: 2 | 3
  }>(),
  { texts: () => ({}), testidPrefix: undefined, card: false, headingLevel: 2 },
)

const emit = defineEmits<{ retry: [] }>()

const DEFAULT_ERROR_MESSAGE =
  'しばらくしてから再試行してください。解消しない場合は api コンテナの状態を確認してください。'

function testid(state: string): string | undefined {
  return props.testidPrefix === undefined ? undefined : `${props.testidPrefix}-state-${state}`
}

const slots = useSlots()

// 読み込み中に画面が自前のスケルトン(`loading` スロット)を渡すときは、スケルトンが自分のカードを持つ(D1 のタイル)ので、
// 外側をカードで包まない(二重の枠にしない)。
const wrapInCard = computed(
  () => props.card && !(props.viewState.kind === 'loading' && slots.loading !== undefined),
)

const isContentKind = computed(() => ['ready', 'stale'].includes(props.viewState.kind))

// 試行時刻: エラーになった時刻と、「再試行」を押した時刻(Query はエラー時刻を ViewState に持たない)。
const attemptedAt = ref(new Date())
watch(
  () => props.viewState.kind,
  (kind) => {
    if (kind === 'error') attemptedAt.value = new Date()
  },
  { immediate: true },
)

function retry(): void {
  attemptedAt.value = new Date()
  emit('retry')
}

// 補助文字: 試行時刻と、想定外のエラーのときだけ診断(`code` と HTTP ステータス。`message` は出さない。E 6.1)。
const errorNote = computed(() => {
  const attempted = `試行時刻 ${formatDate(attemptedAt.value, { withSeconds: true })}`
  const diagnostic = props.viewState.diagnostic
  if (diagnostic === null) return attempted
  return `${attempted} · code: ${diagnostic.code ?? '—'} / HTTP ${diagnostic.status ?? '—'}`
})
</script>

<template>
  <PageAlert
    v-if="viewState.kind === 'stale'"
    type="warning"
    role="alert"
    title="最新の状態を取得できませんでした"
    :class="{ 'view-state-body__stale--in-card': !card }"
    :data-testid="testid('stale')"
  >
    <!-- 文言が画面仕様で決まっている画面(D1)は、`stale-message` スロットで本文を置き換える -->
    <slot name="stale-message">
      <p>
        前回取得したデータ(<TimeText :value="viewState.updatedAt" with-seconds />
        時点)を表示しています。{{ texts.staleNote }}
      </p>
    </slot>
    <template v-if="viewState.canRetry" #actions>
      <v-btn variant="outlined" size="small" :prepend-icon="mdiRefresh" @click="retry"
        >再読み込み</v-btn
      >
    </template>
  </PageAlert>

  <slot v-if="isContentKind" />

  <div v-else :class="{ 'view-state-body__card': wrapInCard }">
    <slot v-if="viewState.kind === 'loading'" name="loading">
      <StateBlock
        kind="loading"
        :loading-label="texts.loadingLabel"
        :data-testid="testid('loading')"
      />
    </slot>
    <StateBlock
      v-else-if="viewState.kind === 'error'"
      kind="error"
      :title="texts.errorTitle ?? 'データを取得できません'"
      :message="texts.errorMessage ?? DEFAULT_ERROR_MESSAGE"
      :note="errorNote"
      :heading-level="headingLevel"
      :data-testid="testid('error')"
    >
      <template v-if="viewState.canRetry || $slots['error-actions']" #default>
        <v-btn
          v-if="viewState.canRetry"
          variant="outlined"
          :prepend-icon="mdiRefresh"
          @click="retry"
          >再試行</v-btn
        >
        <slot name="error-actions" />
      </template>
    </StateBlock>
    <StateBlock
      v-else-if="viewState.kind === 'notfound'"
      kind="notfound"
      :title="texts.notfoundTitle ?? '見つかりません'"
      :message="texts.notfoundMessage"
      :heading-level="headingLevel"
      :data-testid="testid('notfound')"
    >
      <template v-if="$slots['notfound-actions']" #default>
        <slot name="notfound-actions" />
      </template>
    </StateBlock>
    <StateBlock
      v-else
      kind="empty"
      :title="texts.emptyTitle ?? 'データがありません'"
      :message="texts.emptyMessage"
      :heading-level="headingLevel"
      :data-testid="testid('empty')"
    >
      <template v-if="$slots['empty-actions']" #default>
        <slot name="empty-actions" />
      </template>
    </StateBlock>
  </div>
</template>

<style scoped>
/* カードの中(一覧のツールバーの下)では、カードの内側の余白に合わせる。ページにカードがない画面(`card`)では、他のブロックと同じ幅で余白なし
   (続く本文との間隔 16px は、`card` を渡す 3 テンプレート(Dashboard・Detail・Form)が `.page-alert` の下に付ける) */
.view-state-body__stale--in-card {
  margin: 12px 16px;
}
/* ページにカードがないとき、状態ブロックをカードと同じ見た目(境界線・角丸 8px・白面)で包む */
.view-state-body__card {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}
</style>

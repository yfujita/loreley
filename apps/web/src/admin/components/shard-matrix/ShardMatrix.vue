<script setup lang="ts">
// シャード配置のマトリクス(DS 4.15・opensearch 3.3・3.4): 行=ノード(最下部に未割り当て)、列=インデックス。
// 列見出しは 名前 → ドキュメント件数 → 状態タグ。列がカードに収まらないときは、列だけをページ送りする
// (1 ページの列数は、幅から式で決める。`columnsPerPage.ts`)。凡例・件数表示(`role="status"`)・ページ送りを含む。
// 表は全幅で同じ(幅によらず積まない)。表示範囲(ページ)は、先頭の列の名前で覚える(`pageWindow.ts`)。
import { computed, nextTick, ref, useTemplateRef, watch } from 'vue'
import { useDisplay } from 'vuetify'

import { useContainerWidth } from '@/admin/composables/useContainerWidth'
import { mdiAlertOutline } from '@/shared/theme/icons'
import { formatCount } from '@/shared/lib/number'
import StateBlock from '@/shared/ui/StateBlock.vue'
import StatusTag from '@/shared/ui/StatusTag.vue'

import { columnsPerPage, columnWidth, rowHeaderWidth } from './columnsPerPage'
import { resolvePageWindow } from './pageWindow'
import ShardChip from './ShardChip.vue'
import ShardLegend from './ShardLegend.vue'
import ShardPager from './ShardPager.vue'
import type { MatrixColumn, MatrixModel } from './types'

const props = defineProps<{
  /** 絞り込み後のインデックスの列(API の並びのまま)と、それに対する行・凡例 */
  model: MatrixModel
  /** 絞り込み前のインデックスの総数(「全 M 件中」) */
  totalIndexCount: number
  /** 条件が 1 つ以上ある */
  filtered: boolean
  /** 適用中の条件の文(`filtered` のときだけ使う) */
  conditionText: string
  /** 同じ条件なら同じ値。変わったら 1 ページ目に戻る(同じ条件なら、ページを保つ) */
  resetKey: string
}>()

const region = useTemplateRef<HTMLElement>('region')
const scroller = useTemplateRef<HTMLElement>('scroller')
const width = useContainerWidth(region)
// viewport 幅 600px 未満(Vuetify の xs)。行見出し列の幅 H が 152px → 112px になる。
const { xs: narrow } = useDisplay()

const perPage = computed(() => columnsPerPage(width.value, narrow.value))
const columns = computed(() => props.model.columns)
const columnCount = computed(() => columns.value.length)
const isPaged = computed(() => columnCount.value > perPage.value)

// 表示中の先頭の列の名前。null は 1 ページ目。更新・幅の変化では、この名前を含むページを保つ。
const firstName = ref<string | null>(null)
watch(
  () => props.resetKey,
  () => {
    firstName.value = null
  },
)

const pageWindow = computed(() =>
  resolvePageWindow({
    names: columns.value.map((column) => column.name),
    perPage: perPage.value,
    firstName: firstName.value,
  }),
)
const visibleColumns = computed<readonly MatrixColumn[]>(() =>
  columns.value.slice(pageWindow.value.firstIndex, pageWindow.value.firstIndex + perPage.value),
)

function goToPage(page: number): void {
  firstName.value = columns.value[(page - 1) * perPage.value]?.name ?? null
}

const columnWidthPx = computed(() =>
  columnWidth({
    width: width.value,
    narrow: narrow.value,
    perPage: perPage.value,
    columnCount: columnCount.value,
  }),
)
const rowHeaderWidthPx = computed(() => rowHeaderWidth(narrow.value))
const tableWidthPx = computed(
  () => rowHeaderWidthPx.value + visibleColumns.value.length * columnWidthPx.value,
)

// 件数表示・補足・表の caption(読み上げ)用の範囲。
const rangeFrom = computed(() => pageWindow.value.firstIndex + 1)
const rangeTo = computed(() => pageWindow.value.firstIndex + visibleColumns.value.length)
const hasSingleColumnRange = computed(() => rangeFrom.value === rangeTo.value)
// 件数はすべて 3 桁区切り(DS 4.9。切り詰め後の 1,000 件のとき「1,000」になる)。
const rangeText = computed(() =>
  hasSingleColumnRange.value
    ? formatCount(rangeTo.value)
    : `${formatCount(rangeFrom.value)}–${formatCount(rangeTo.value)}`,
)
const rangePrefix = computed(() => (isPaged.value ? `${rangeText.value} / ` : ''))
const pageLabel = computed(
  () =>
    `(ページ ${formatCount(pageWindow.value.page)} / ${formatCount(pageWindow.value.pageCount)})`,
)
const columnCountText = computed(() => formatCount(columnCount.value))
const totalCountText = computed(() => formatCount(props.totalIndexCount))

// 件数表示(`role="status"`)の文。N=絞り込み後、M=全件。「絞り込み後 N 件のインデックス」「(全 M 件中)」は塊として折り返さない。
const countText = computed(() => {
  const suffix = `(全 ${totalCountText.value} 件中)`
  if (columnCount.value === 0) {
    return { prefix: '', main: '絞り込み後 0 件のインデックス', suffix, readout: '' }
  }
  const readout = isPaged.value ? pageLabel.value : ''
  if (props.filtered) {
    return {
      prefix: rangePrefix.value,
      main: `絞り込み後 ${columnCountText.value} 件のインデックス`,
      suffix,
      readout,
    }
  }
  const main = isPaged.value
    ? `全 ${columnCountText.value} 件のインデックス`
    : `${columnCountText.value} 件のインデックス`
  return { prefix: rangePrefix.value, main, suffix: '', readout }
})

const hasUnavailableCount = computed(() =>
  visibleColumns.value.some((column) => column.documentCount === null),
)
const sumReadout = computed(() =>
  props.filtered ? '(絞り込み後のインデックスの合計)' : '(全インデックスの合計)',
)

const tableCaption = computed(() => {
  const rows = props.model.unassignedShardCount > 0 ? 'ノードと未割り当て' : 'ノード'
  const parts = [
    `シャードの配置。行は${rows}、列はインデックス(列見出しにインデックス名・ドキュメント件数・状態)。`,
  ]
  if (props.filtered) {
    parts.push(`絞り込み後 ${columnCountText.value} 件(全 ${totalCountText.value} 件中)。`)
  }
  if (isPaged.value) {
    const total = props.filtered ? '' : `全 ${columnCountText.value} 件のうち `
    const range = hasSingleColumnRange.value
      ? `${formatCount(rangeFrom.value)} 件目`
      : `${formatCount(rangeFrom.value)}〜${formatCount(rangeTo.value)} 件目`
    parts.push(`${total}${range}を表示中${pageLabel.value}。`)
  }
  parts.push('状態の悪い順、同じ状態は名前の昇順。')
  return parts.join('')
})

// 収まらないとき(ブラウザの拡大・文字サイズの拡大)だけ、表の外側がスクロールできる。そのときだけキーボードで到達できるようにする。
const isScrollable = ref(false)
function measureScrollable(): void {
  const element = scroller.value
  isScrollable.value = element !== null && element.scrollWidth > element.clientWidth
}
watch([tableWidthPx, width, visibleColumns, narrow], () => nextTick(measureScrollable), {
  flush: 'post',
})
</script>

<template>
  <div
    ref="region"
    class="shard-matrix"
    role="group"
    aria-label="シャードの配置(行はノード、列はインデックス)"
    data-testid="o1-shards"
  >
    <ShardLegend v-if="columnCount > 0" :legend="model.legend" />

    <div class="shard-matrix__bar">
      <div class="shard-matrix__info">
        <p
          class="shard-matrix__count"
          role="status"
          aria-live="polite"
          aria-atomic="true"
          data-testid="o1-count"
        >
          {{ countText.prefix }}<span class="shard-matrix__nb">{{ countText.main }}</span
          ><span v-if="countText.suffix !== ''" class="shard-matrix__nb shard-matrix__suffix">{{
            countText.suffix
          }}</span
          ><span v-if="countText.readout !== ''" class="sr-only">{{ countText.readout }}</span>
        </p>
        <p class="shard-matrix__note text-caption-sm text-on-surface-variant">
          <template v-if="columnCount > 0">
            <span>インデックス名の下の数はドキュメント件数。</span>
            <span>状態の悪い順(同じ状態は名前の昇順)。</span>
          </template>
          <span v-if="filtered"
            >適用中の条件: {{ conditionText }}。概況はクラスタ全体の値で、絞り込みの対象外。</span
          >
          <span v-if="hasUnavailableCount">見出しの「—」は件数を取得できません。</span>
        </p>
      </div>
      <ShardPager
        v-if="isPaged"
        :page="pageWindow.page"
        :page-count="pageWindow.pageCount"
        @update:page="goToPage"
      />
    </div>

    <StateBlock
      v-if="columnCount === 0"
      kind="empty"
      title="条件に合うインデックスがありません"
      message="インデックス名や状態の条件を変えるか、上のフォームの「条件を解除」で条件を外してください。"
      :heading-level="3"
      data-testid="o1-state-nomatch"
    />

    <div
      v-else
      ref="scroller"
      class="shard-matrix__scroll"
      :tabindex="isScrollable ? 0 : undefined"
      :role="isScrollable ? 'region' : undefined"
      :aria-label="isScrollable ? 'シャードの配置(横にスクロールできます)' : undefined"
    >
      <table class="shard-matrix__table" :style="{ width: `${tableWidthPx}px` }">
        <caption class="sr-only">
          {{
            tableCaption
          }}
        </caption>
        <colgroup>
          <col :style="{ width: `${rowHeaderWidthPx}px` }" />
          <col
            v-for="column in visibleColumns"
            :key="column.name"
            :style="{ width: `${columnWidthPx}px` }"
          />
        </colgroup>
        <thead>
          <tr>
            <th scope="col" class="shard-matrix__corner">ノード</th>
            <th
              v-for="column in visibleColumns"
              :key="column.name"
              scope="col"
              class="shard-matrix__index"
            >
              <div class="shard-matrix__index-inner">
                <span class="shard-matrix__index-name">{{ column.name }}</span>
                <span
                  v-if="column.documentCount !== null"
                  class="shard-matrix__doc-count"
                  :data-testid="`o1-count-${column.name}`"
                >
                  <span class="sr-only">ドキュメント </span
                  ><span class="shard-matrix__doc-number">{{
                    formatCount(column.documentCount)
                  }}</span
                  ><span class="shard-matrix__doc-unit"> 件</span>
                </span>
                <span
                  v-else
                  class="shard-matrix__doc-count shard-matrix__none"
                  :data-testid="`o1-count-${column.name}`"
                  >—<span class="sr-only">ドキュメント件数を取得できません</span></span
                >
                <StatusTag v-if="column.status !== null" kind="index" :value="column.status" />
                <span v-else class="shard-matrix__none"
                  >—<span class="sr-only">状態を取得できません</span></span
                >
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="node in model.nodes" :key="node.name">
            <th scope="row" class="shard-matrix__node">
              <span class="shard-matrix__node-name">{{ node.name }}</span>
              <span class="text-caption-sm text-on-surface-variant"
                >シャード {{ formatCount(node.shardCount)
                }}<span class="sr-only">{{ sumReadout }}</span></span
              >
            </th>
            <td v-for="column in visibleColumns" :key="column.name">
              <span v-if="column.shardsByNode.get(node.name)" class="shard-matrix__chips">
                <ShardChip
                  v-for="chip in column.shardsByNode.get(node.name)"
                  :key="`${chip.role}-${chip.number}`"
                  :chip="chip"
                />
              </span>
              <span v-else class="shard-matrix__none"
                >—<span class="sr-only">シャードなし</span></span
              >
            </td>
          </tr>
          <tr v-if="model.unassignedShardCount > 0" class="shard-matrix__unassigned">
            <th scope="row" class="shard-matrix__node">
              <span class="shard-matrix__unassigned-label">
                <v-icon :icon="mdiAlertOutline" size="16" />未割り当て
              </span>
              <span class="text-caption-sm"
                >シャード {{ formatCount(model.unassignedShardCount)
                }}<span class="sr-only">{{ sumReadout }}</span></span
              >
            </th>
            <td v-for="column in visibleColumns" :key="column.name">
              <span v-if="column.unassigned.length > 0" class="shard-matrix__chips">
                <ShardChip
                  v-for="chip in column.unassigned"
                  :key="`${chip.role}-${chip.number}`"
                  :chip="chip"
                />
              </span>
              <span v-else class="shard-matrix__none"
                >—<span class="sr-only">シャードなし</span></span
              >
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
/* マトリクスの領域はカードの左右の端まで全幅(カードの内側余白を設けない)。この幅が 1 ページの列数の W になる */
.shard-matrix {
  min-width: 0;
}
.shard-matrix__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  min-height: 52px;
  padding: 8px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
/* 補足の文が長くても、ページ送りを下へ折り返す前に、文のほうを折り返す */
.shard-matrix__info {
  flex: 1 1 20rem;
  min-width: 0;
}
.shard-matrix__info p {
  margin: 0;
}
.shard-matrix__count {
  font-weight: 600;
}
/* 「(全 M 件中)」などは 1 つの塊として扱い、途中で折り返さない */
.shard-matrix__nb {
  display: inline-block;
}
.shard-matrix__suffix {
  margin-left: 0.25em;
}
.shard-matrix__note > span {
  margin-right: 0.5em;
}
.shard-matrix__scroll {
  overflow-x: auto;
}
.shard-matrix__table {
  table-layout: fixed;
  border-collapse: separate;
  border-spacing: 0;
}
.shard-matrix__table th,
.shard-matrix__table td {
  padding: 8px;
  vertical-align: top;
  text-align: left;
  font-weight: 400;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-left: 1px solid rgba(var(--v-border-color), 0.08);
}
.shard-matrix__table td {
  height: 48px;
}
.shard-matrix__table thead th {
  border-top: 0;
  background: rgb(var(--v-theme-surface-variant));
  /* 見出しの高さをそろえる(状態タグを下端にそろえる土台) */
  height: 1px;
}
/* 左端の行見出し列(ノード)は固定。収まらないとき、行見出しを残して列だけがスクロールする */
.shard-matrix__corner,
.shard-matrix__node {
  position: sticky;
  left: 0;
  z-index: 1;
  border-left: 0 !important;
  box-shadow: 1px 0 0 rgba(var(--v-border-color), var(--v-border-opacity));
}
.shard-matrix__corner {
  padding: 8px 12px !important;
  vertical-align: bottom !important;
  font-size: 0.75rem;
  font-weight: 600 !important;
  color: rgb(var(--v-theme-on-surface-variant));
}
.shard-matrix__node {
  padding: 8px 12px !important;
  background: rgb(var(--v-theme-surface));
}
.shard-matrix__node-name {
  display: block;
  font-family: var(--font-mono);
  font-weight: 600;
  overflow-wrap: anywhere;
}
.shard-matrix__node .text-caption-sm {
  display: block;
}
.shard-matrix__index-inner {
  display: grid;
  grid-template-rows: auto auto 1fr;
  justify-items: start;
  align-content: stretch;
  gap: 4px;
  height: 100%;
}
.shard-matrix__index-inner :deep(.status-tag) {
  align-self: end;
}
.shard-matrix__index-name {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  line-height: 1.4;
  font-weight: 600;
  overflow-wrap: anywhere;
  color: rgb(var(--v-theme-on-surface));
}
.shard-matrix__doc-count {
  font-size: 0.75rem;
  line-height: 1.4;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--v-theme-on-surface));
}
/* 数字は途中で折り返さない。単位「件」だけが折り返すのは許容(10 桁以上) */
.shard-matrix__doc-number {
  white-space: nowrap;
}
.shard-matrix__doc-unit {
  color: rgb(var(--v-theme-on-surface-variant));
}
.shard-matrix__none {
  color: rgb(var(--v-theme-on-surface-variant));
}
.shard-matrix__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
/* 未割り当ての行: 最下部・点線の区切り・warning-container の面 */
.shard-matrix__unassigned td {
  background: rgba(var(--v-theme-warning-container), 0.4);
  border-top: 1px dashed rgb(var(--v-theme-warning));
}
.shard-matrix__unassigned .shard-matrix__node {
  background: rgb(var(--v-theme-warning-container));
  color: rgb(var(--v-theme-on-warning-container));
  border-top: 1px dashed rgb(var(--v-theme-warning));
}
.shard-matrix__unassigned .text-caption-sm {
  color: rgb(var(--v-theme-on-warning-container));
}
.shard-matrix__unassigned-label {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-weight: 600;
}
.shard-matrix__unassigned-label .v-icon {
  margin-top: 2px;
  color: rgb(var(--v-theme-warning));
}
@media (max-width: 599px) {
  .shard-matrix__bar {
    padding: 8px 12px;
  }
  .shard-matrix__corner,
  .shard-matrix__node {
    padding: 8px !important;
  }
}
</style>

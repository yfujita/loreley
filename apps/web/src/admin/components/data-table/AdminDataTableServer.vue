<script setup lang="ts" generic="T extends Record<string, unknown>">
// データテーブル(サーバー側のページング・並べ替え。DS 4.3): 件数が多い一覧(ジョブ・文書)用。
// `VDataTableServer` を、`AdminDataTable` と同じ props・イベントの形で使えるように包む(FMOD-U-4)。
//
// 差の吸収:
// - `VDataTableServer` の `@update:options` は初期表示でも 1 回発火する(確認 FARC-U-2)ので使わない。
//   ページ・件数・並べ替えは、変更があったときだけ発火する個別のイベント(`update:page` など)で受け、
//   条件の唯一の正は呼び出し側(URL の `params`。E 5.6)に置く(初期表示で二重に取得しない)。
// - 並べ替えは単一列(`multi-sort` を使わない)。
// - 取得中は前回のデータを保持する(`placeholderData: keepPreviousData` は Query 側。E 5.6)。
import { computed } from 'vue'

import SkeletonRows from './SkeletonRows.vue'
import {
  fromVuetifySortBy,
  toVuetifyHeaders,
  toVuetifySortBy,
  type AdminColumn,
  type AdminSort,
  type VuetifySortItem,
} from './tableModel'
import './dataTable.css'

const props = withDefaults(
  defineProps<{
    columns: readonly AdminColumn[]
    items: readonly T[]
    /** 条件に合う全件数(ページングの「N 件」) */
    itemsLength: number
    itemKey: keyof T & string
    /** 視覚的に隠す `<caption>`(DS 8) */
    caption: string
    page: number
    itemsPerPage: 25 | 50 | 100
    sort?: AdminSort
    mustSort?: boolean
    loading?: boolean
    rowTestid?: (item: T) => string | undefined
  }>(),
  { sort: null, mustSort: false, loading: false, rowTestid: undefined },
)

const emit = defineEmits<{
  'update:page': [page: number]
  'update:itemsPerPage': [itemsPerPage: 25 | 50 | 100]
  'update:sort': [sort: AdminSort]
}>()

const headers = computed(() => toVuetifyHeaders(props.columns, props.sort))
const sortBy = computed(() => toVuetifySortBy(props.sort))

function onSortBy(value: VuetifySortItem[]): void {
  emit('update:sort', fromVuetifySortBy(value))
}

function onItemsPerPage(value: number): void {
  if (value === 25 || value === 50 || value === 100) emit('update:itemsPerPage', value)
}

function rowProps(data: { item: T }): Record<string, string | undefined> {
  return { 'data-testid': props.rowTestid?.(data.item) }
}
</script>

<template>
  <v-data-table-server
    class="admin-data-table"
    :headers="headers"
    :items="items as T[]"
    :items-length="itemsLength"
    :item-value="itemKey"
    :page="page"
    :items-per-page="itemsPerPage"
    :items-per-page-options="[25, 50, 100]"
    items-per-page-text="1 ページの件数"
    :show-first-last-page="false"
    :hide-default-footer="loading"
    page-text="{0}–{1} / {2} 件"
    :sort-by="sortBy"
    :mobile="null"
    :must-sort="mustSort"
    :row-props="rowProps"
    :aria-busy="loading ? 'true' : undefined"
    @update:page="emit('update:page', $event)"
    @update:items-per-page="onItemsPerPage"
    @update:sort-by="onSortBy"
  >
    <template #caption>
      <caption class="sr-only">
        {{
          caption
        }}
      </caption>
    </template>
    <template v-if="loading" #body>
      <SkeletonRows :column-count="columns.length" />
    </template>
    <template v-for="(_, slotName) in $slots" :key="slotName" #[slotName]="slotProps">
      <slot :name="slotName" v-bind="slotProps ?? {}" />
    </template>
  </v-data-table-server>
</template>

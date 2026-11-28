// provide / inject のキー(F 3.5)。`templates`(層 3)が `shell`(層 4)を import せずに、パンくずを受け取るため。
import type { InjectionKey, Ref } from 'vue'

/** パンくずの 1 項目。`to` が null の項目は現在のページ(リンクにしない。`aria-current="page"`。DS 5.2)。 */
export type BreadcrumbItem = {
  title: string
  to: string | null
}

/** `AppShell` が `useBreadcrumbs` で作って provide し、`PageHeader` が inject する。 */
export const breadcrumbsKey: InjectionKey<Readonly<Ref<readonly BreadcrumbItem[]>>> =
  Symbol('breadcrumbs')

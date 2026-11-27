// クロールの起動(EP-06 `startCrawl`)。DLG-1 と DLG-4(失敗ジョブの再実行)が共有する。
// 本文は呼び出し側が常に `{ force_delete, rewrite_mode }` を渡す(E 7.5。`null` は `false` にして渡す)。
import { startCrawlMutation } from '@/admin/api'
import { useInvalidatingMutation } from '@/admin/queries/invalidation'

export function useStartCrawlMutation() {
  return useInvalidatingMutation(startCrawlMutation(), 'startCrawl')
}

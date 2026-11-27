// 画面の状態(E 6.2・F 3.7。FMOD-P-27)。`features` の composable が `useViewState` で作り、
// `templates` は `viewState` だけを props で受けて描く(`error.code` を判定しない。R7)。
//
// Query の状態と `describeError` の結果から、次のどれかに決める。写像の表は E 6.2。

export type ViewStateKind =
  // 初回の読み込み中(データなしで取得中): スケルトン+`aria-busy`
  | 'loading'
  // 空(成功・0 件): 空ブロック
  | 'empty'
  // エラー(データなし): エラーブロック+「再試行」
  | 'error'
  // 見つかりません(データの有無を問わない。前回データがあっても stale にしない)
  | 'notfound'
  // 古いデータ(再取得に失敗・前回のデータあり): warning アラート+前回のデータ+「再読み込み」
  | 'stale'
  // 通常の表示
  | 'ready'

/** 診断用の補助文字(想定外のエラー)。`code` と HTTP ステータスだけで、`message`・入力値・パスは含まない。 */
export type ViewDiagnostic = { code: string | null; status: number | null }

export type ViewState = {
  kind: ViewStateKind
  /** 再取得中(データあり・取得中): データは消さず、カード上端に進行バー */
  isRefreshing: boolean
  /** 最終更新(成功)時刻(`dataUpdatedAt`。ミリ秒)。データがないとき null */
  updatedAt: number | null
  /** 「再試行」(`refetch`)・「再読み込み」を出すか */
  canRetry: boolean
  /** 想定外のエラーのときだけ。code と HTTP ステータス */
  diagnostic: ViewDiagnostic | null
}

/** `describeError` の結果のうち、状態の決定に使う部分。lib は `admin/api` の値を import できないので、構造で受ける。 */
export type DescribedReadError = {
  notFound: boolean
  retryable: boolean
  unexpected: boolean
  diagnostic: ViewDiagnostic
}

export type ViewStateInput = {
  /** 取得中かつデータなし(TanStack Query v5 の `isLoading`。`enabled: false` では false。FARC-U-26 の (4)) */
  isLoading: boolean
  isFetching: boolean
  hasData: boolean
  /** データがあり、0 件のとき */
  isEmpty: boolean
  /** データなしの失敗(`isLoadingError`) */
  isLoadingError: boolean
  /** データありの再取得の失敗(`isRefetchError`) */
  isRefetchError: boolean
  /** `dataUpdatedAt`(データがないとき 0) */
  dataUpdatedAt: number
  /** `describeError` の結果。エラーがないとき null */
  error: DescribedReadError | null
  /** パスの ID が `isValidPathId` で不正なとき。API を呼ばず「見つかりません」と同じにする(E 5.3) */
  invalidPathId?: boolean
}

export function resolveViewState(input: ViewStateInput): ViewState {
  const updatedAt = input.hasData && input.dataUpdatedAt > 0 ? input.dataUpdatedAt : null
  const isRefreshing = input.hasData && input.isFetching
  const diagnostic = input.error?.unexpected === true ? input.error.diagnostic : null
  const base = { isRefreshing, updatedAt, canRetry: false, diagnostic }

  // 見つかりません: データの有無を問わない(消えたリソースを「最新ではない」と読ませない)。
  if (input.invalidPathId === true || input.error?.notFound === true) {
    return { ...base, kind: 'notfound', isRefreshing: false, diagnostic: null }
  }
  if (input.isLoadingError) {
    return { ...base, kind: 'error', canRetry: input.error?.retryable ?? true }
  }
  if (input.isRefetchError) {
    return { ...base, kind: 'stale', canRetry: input.error?.retryable ?? true }
  }
  if (input.isLoading) {
    return { ...base, kind: 'loading', diagnostic: null }
  }
  if (!input.hasData) {
    // 取得していない(`enabled: false`)。表示する値がないので空として扱う。
    // 呼び出し側(X1 のソース未選択など)は、この状態になる前に自分の状態(「データソースを選択」など)を先に判定する前提。
    // 6 種の kind に「未取得(idle)」は足さない(足す案はフェーズ 6 以降で再検討)。
    return { ...base, kind: 'empty', diagnostic: null }
  }
  return { ...base, kind: input.isEmpty ? 'empty' : 'ready', diagnostic: null }
}

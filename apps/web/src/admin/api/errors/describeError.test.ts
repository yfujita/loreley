import { describe, expect, it } from 'vitest'

import type { ApiError } from '@/shared/api/apiError'

import { describeError, type ErrorContext, type WriteOperation } from './describeError'
import { ADMIN_ERROR_CODES, COMMON_ERROR_CODES, type KnownErrorCode } from './errorTable'

const READ: ErrorContext = { operation: 'read' }
const ALL_WRITE_OPERATIONS: WriteOperation[] = [
  'registerSource',
  'updateSource',
  'startSourceDelete',
  'startCrawl',
  'cancelJob',
  'releaseLock',
]
const SAVE_OPERATIONS: WriteOperation[] = ['registerSource', 'updateSource']
const DIALOG_OPERATIONS: WriteOperation[] = [
  'startSourceDelete',
  'startCrawl',
  'cancelJob',
  'releaseLock',
]

function apiError(
  code: string,
  options: { status?: number; retryable?: boolean; details?: Record<string, unknown> } = {},
): ApiError {
  return {
    kind: 'api',
    status: options.status ?? 400,
    code,
    retryable: options.retryable ?? false,
    ...(options.details !== undefined && { details: options.details }),
    outcomeUnknown: options.details?.outcome_unknown === true,
  }
}

describe('読み取り(E 6.2)', () => {
  it.each([
    ['source_config_not_found', 404],
    ['job_not_found', 404],
    ['invalid_request', 400],
    ['not_found', 404],
  ])('%s は「見つかりません」(データの有無を問わない。再試行を出さない)', (code, status) => {
    const description = describeError(apiError(code, { status }), READ)

    expect(description).toMatchObject({
      target: 'state-block',
      notFound: true,
      retryable: false,
      outcomeUnknown: false,
    })
  })

  it('unavailable(503)はエラーブロックまたは stale(再試行を出す。想定外ではない)', () => {
    const description = describeError(
      apiError('unavailable', { status: 503, retryable: true }),
      READ,
    )

    expect(description).toMatchObject({
      target: 'state-block',
      notFound: false,
      retryable: true,
      unexpected: false,
      diagnostic: { code: 'unavailable', status: 503 },
    })
  })

  it.each(['internal_error', 'http_error', 'method_not_allowed', 'crawler_error'])(
    '%s は想定外(一般的な文言+診断。code と HTTP ステータス)',
    (code) => {
      const description = describeError(apiError(code, { status: 500 }), READ)

      expect(description).toMatchObject({
        notFound: false,
        unexpected: true,
        retryable: true,
        diagnostic: { code, status: 500 },
      })
    },
  )

  it('未知の code も想定外', () => {
    expect(describeError(apiError('something_new', { status: 418 }), READ)).toMatchObject({
      unexpected: true,
      diagnostic: { code: 'something_new', status: 418 },
    })
  })

  it('network・timeout は再試行できる(想定外ではない)', () => {
    for (const error of [{ kind: 'network' }, { kind: 'timeout' }]) {
      expect(describeError(error, READ)).toMatchObject({
        target: 'state-block',
        retryable: true,
        unexpected: false,
        outcomeUnknown: false,
        diagnostic: { code: null, status: null },
      })
    }
  })

  it('invalid_response(Nginx の HTML)は想定外。診断は HTTP ステータスだけ(code なし)', () => {
    expect(describeError({ kind: 'invalid_response', status: 502 }, READ)).toMatchObject({
      retryable: true,
      unexpected: true,
      diagnostic: { code: null, status: 502 },
    })
    expect(describeError({ kind: 'invalid_response' }, READ).diagnostic).toEqual({
      code: null,
      status: null,
    })
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['文字列', '<html>'],
    [
      '生成型の ErrorResponse(正規化されていない生の本文)',
      { error: { code: 'x', message: '', retryable: false } },
    ],
    ['Error', new Error('x')],
  ])('ApiError でない値(%s)は invalid_response(status なし)として扱う', (_name, value) => {
    expect(describeError(value, READ)).toMatchObject({
      unexpected: true,
      retryable: true,
      diagnostic: { code: null, status: null },
    })
  })
})

describe('書き込み: 結果不明(E 6.5)', () => {
  it.each(ALL_WRITE_OPERATIONS)(
    '%s: network・timeout・invalid_response(502・504 を含め status を問わない)は結果不明で、再試行を出さない',
    (operation) => {
      const errors: ApiError[] = [
        { kind: 'network' },
        { kind: 'timeout' },
        { kind: 'invalid_response' },
        { kind: 'invalid_response', status: 502 },
        { kind: 'invalid_response', status: 504 },
        { kind: 'invalid_response', status: 413 },
      ]
      for (const error of errors) {
        expect(describeError(error, { operation })).toMatchObject({
          outcomeUnknown: true,
          retryable: false,
          unexpected: false,
          variant: 'warning',
        })
      }
    },
  )

  it.each(SAVE_OPERATIONS)(
    '%s(保存系)は再送が安全なので「もう一度保存」を出してよい',
    (operation) => {
      expect(describeError({ kind: 'timeout' }, { operation })).toMatchObject({
        target: 'form-alert',
        outcomeUnknown: true,
        resendSafe: true,
      })
    },
  )

  it.each(DIALOG_OPERATIONS)(
    '%s(起動・取消・解放)は再送の導線ではなく、確認の導線(resendSafe=false)',
    (operation) => {
      expect(describeError({ kind: 'network' }, { operation })).toMatchObject({
        target: 'dialog-alert',
        outcomeUnknown: true,
        resendSafe: false,
      })
    },
  )

  it.each(ALL_WRITE_OPERATIONS)(
    '%s: crawler_response_lost(504)は結果不明。details.outcome_unknown がなくても結果不明',
    (operation) => {
      const withDetails = describeError(
        apiError('crawler_response_lost', { status: 504, details: { outcome_unknown: true } }),
        { operation },
      )
      const withoutDetails = describeError(apiError('crawler_response_lost', { status: 504 }), {
        operation,
      })

      for (const description of [withDetails, withoutDetails]) {
        expect(description).toMatchObject({
          outcomeUnknown: true,
          retryable: false,
          unexpected: false,
          variant: 'warning',
        })
      }
    },
  )
})

describe('書き込み: code ごとの扱い(E 6.3)', () => {
  const START_CRAWL: ErrorContext = { operation: 'startCrawl' }

  it.each([
    ['crawler_unavailable', 503],
    ['crawler_unreachable', 503],
  ])('%s(retryable)は再試行を出す(想定内)', (code, status) => {
    expect(describeError(apiError(code, { status, retryable: true }), START_CRAWL)).toMatchObject({
      target: 'dialog-alert',
      retryable: true,
      outcomeUnknown: false,
      unexpected: false,
    })
  })

  it('crawler_error(502)は想定外で、再試行を出さない', () => {
    expect(describeError(apiError('crawler_error', { status: 502 }), START_CRAWL)).toMatchObject({
      unexpected: true,
      retryable: false,
      diagnostic: { code: 'crawler_error', status: 502 },
    })
  })

  it.each(['source_deleting', 'maintenance_enabled', 'source_config_not_found'])(
    '%s はダイアログ内アラート(error。次の行動なし・想定内)',
    (code) => {
      const status = code === 'source_config_not_found' ? 404 : 409

      expect(describeError(apiError(code, { status }), START_CRAWL)).toMatchObject({
        target: 'dialog-alert',
        variant: 'error',
        retryable: false,
        unexpected: false,
      })
    },
  )

  it('source_deleting の S4 の保存はフォーム上部のアラート', () => {
    expect(
      describeError(apiError('source_deleting', { status: 409 }), { operation: 'updateSource' }),
    ).toMatchObject({ target: 'form-alert' })
  })

  it('job_not_cancellable は想定外(画面は cancellable=false の行に操作を出さない)', () => {
    expect(
      describeError(apiError('job_not_cancellable', { status: 409 }), { operation: 'cancelJob' }),
    ).toMatchObject({ target: 'dialog-alert', unexpected: true })
  })

  it('job_already_finished は成功扱い', () => {
    expect(
      describeError(
        apiError('job_already_finished', { status: 409, details: { status: 'failed' } }),
        {
          operation: 'cancelJob',
        },
      ),
    ).toMatchObject({ target: 'success', unexpected: false })
  })

  it.each([
    ['held_crawl', 'error'],
    ['held_delete', 'error'],
    ['lease_expired', 'warning'],
    ['orphan', 'warning'],
    ['just_acquired', 'error'],
    ['unknown', 'error'],
  ] as const)('lock_held の lock_state=%s → variant %s', (lockState, variant) => {
    const description = describeError(
      apiError('lock_held', { status: 409, details: { lock_state: lockState } }),
      START_CRAWL,
    )

    expect(description).toMatchObject({
      target: 'dialog-alert',
      variant,
      lockState,
      unexpected: false,
      retryable: false,
    })
  })

  it.each([
    ['orphan', 'warning'],
    ['lease_expired', 'warning'],
    ['just_acquired', 'error'],
    ['held_crawl', 'error'],
    ['held_delete', 'error'],
    ['unknown', 'error'],
  ] as const)('lock_in_use(EP-08)も lock_state=%s の variant(%s)を使う', (lockState, variant) => {
    const description = describeError(
      apiError('lock_in_use', { status: 409, details: { lock_state: lockState } }),
      { operation: 'releaseLock' },
    )

    expect(description).toMatchObject({ target: 'dialog-alert', variant, lockState })
  })

  it('lock_state がない・未知の値のときは error(lockState は null)', () => {
    for (const details of [undefined, { lock_state: 'bogus' }, { lock_state: 3 }]) {
      expect(
        describeError(
          apiError('lock_held', { status: 409, ...(details && { details }) }),
          START_CRAWL,
        ),
      ).toMatchObject({ variant: 'error', lockState: null })
    }
  })
})

describe('書き込み: 項目別エラー(S3・S4。E 6.3・6.4)', () => {
  const REGISTER: ErrorContext = { operation: 'registerSource' }
  const errors = [
    { field: 'ttl_days', reason: 'range' },
    {
      field: 'connector_config.include_patterns[2]',
      reason: 'config_invalid',
      detail: '`\\` を含む',
    },
  ]

  it('invalid_request で details.errors があるとき、項目別(fieldErrors を返す)', () => {
    const description = describeError(
      apiError('invalid_request', { details: { errors } }),
      REGISTER,
    )

    expect(description).toMatchObject({ target: 'field', unexpected: false })
    expect(description.fieldErrors).toEqual([
      { field: 'ttl_days', reason: 'range', detail: null },
      {
        field: 'connector_config.include_patterns[2]',
        reason: 'config_invalid',
        detail: '`\\` を含む',
      },
    ])
  })

  it.each([
    ['details がない(本文が JSON として読めない・1 MiB 超など)', undefined],
    ['errors がない', { other: 1 }],
    ['errors が空', { errors: [] }],
  ])('invalid_request で %s は想定外のフォーム上部アラート(診断つき)', (_name, details) => {
    const description = describeError(
      apiError('invalid_request', { ...(details && { details }) }),
      REGISTER,
    )

    expect(description).toMatchObject({
      target: 'form-alert',
      unexpected: true,
      fieldErrors: [],
      diagnostic: { code: 'invalid_request', status: 400 },
    })
  })

  it.each(DIALOG_OPERATIONS)('invalid_request は %s では想定外(画面が送らない値)', (operation) => {
    expect(
      describeError(apiError('invalid_request', { details: { errors } }), { operation }),
    ).toMatchObject({ target: 'dialog-alert', unexpected: true })
  })

  it('config_invalid で errors があるとき項目別、crawler_message も返す', () => {
    const description = describeError(
      apiError('config_invalid', {
        details: { errors: [errors[1]], crawler_message: 'include_patterns[2]: x' },
      }),
      REGISTER,
    )

    expect(description).toMatchObject({
      target: 'field',
      unexpected: false,
      crawlerMessage: 'include_patterns[2]: x',
    })
    expect(description.fieldErrors).toHaveLength(1)
  })

  it('config_invalid で errors が空(分解不能)は、想定外ではなく上部アラートに crawler_message', () => {
    const description = describeError(
      apiError('config_invalid', { details: { errors: [], crawler_message: 'root: x' } }),
      REGISTER,
    )

    expect(description).toMatchObject({
      target: 'form-alert',
      unexpected: false,
      crawlerMessage: 'root: x',
      fieldErrors: [],
    })
  })

  it('source_already_exists は識別子の項目の下(details.status を持つ)', () => {
    expect(
      describeError(
        apiError('source_already_exists', { status: 409, details: { status: 'deleting' } }),
        REGISTER,
      ),
    ).toMatchObject({ target: 'field', unexpected: false })
  })

  it('details.errors の不正な要素は捨てる(field・reason が string でないもの)', () => {
    const description = describeError(
      apiError('invalid_request', {
        details: {
          errors: [
            null,
            'x',
            { field: 1, reason: 'range' },
            { field: 'a' },
            { field: 'b', reason: 'type' },
          ],
        },
      }),
      REGISTER,
    )

    expect(description.fieldErrors).toEqual([{ field: 'b', reason: 'type', detail: null }])
  })

  it('crawler_message が string でないとき null', () => {
    expect(
      describeError(apiError('config_invalid', { details: { crawler_message: 5 } }), REGISTER)
        .crawlerMessage,
    ).toBeNull()
  })
})

describe('全 20 code × 読み取り・書き込み', () => {
  const ALL_CODES: KnownErrorCode[] = [...ADMIN_ERROR_CODES, ...COMMON_ERROR_CODES]

  it.each(ALL_CODES)(
    '%s: どの文脈でも記述を返し、診断に code が入る(入力値・パスは含まない)',
    (code) => {
      for (const context of [READ, ...ALL_WRITE_OPERATIONS.map((operation) => ({ operation }))]) {
        const description = describeError(apiError(code, { status: 500 }), context)

        expect(description.diagnostic).toEqual({ code, status: 500 })
      }
    },
  )

  it('読み取りで「見つかりません」になる code は 4 種だけ', () => {
    const notFound = ALL_CODES.filter((code) => describeError(apiError(code), READ).notFound)

    expect([...notFound].sort()).toEqual([
      'invalid_request',
      'job_not_found',
      'not_found',
      'source_config_not_found',
    ])
  })

  it('書き込みで想定内の再試行(retryable=true の応答)を出すのは、retryable を持つ応答だけ', () => {
    for (const code of ALL_CODES) {
      const retryable = describeError(apiError(code, { retryable: true }), {
        operation: 'startCrawl',
      }).retryable
      const notRetryable = describeError(apiError(code, { retryable: false }), {
        operation: 'startCrawl',
      }).retryable

      expect(notRetryable, `${code}: retryable=false の応答で再試行を出さない`).toBe(false)
      // 結果不明の code は、retryable=true と返ってきても再試行を出さない(確認の導線を出す)
      expect(retryable, code).toBe(code !== 'crawler_response_lost')
    }
  })
})

// E 6.3 の表からの手書きの期待値(実装のコピーにしない)。20 code × {読み取り・フォーム(S3 の保存)・ダイアログ(DLG-1 の起動)}。
describe('20 code × 文脈の期待値(E 6.2・6.3・6.5)', () => {
  const FORM: ErrorContext = { operation: 'registerSource' }
  const DIALOG: ErrorContext = { operation: 'startCrawl' }

  type Expected = { target: string; variant: string; unexpected: boolean }
  type Row = {
    code: KnownErrorCode
    status: number
    /** 入力に付ける details(項目別・lock_state・結果不明など、その code が実際に運ぶもの) */
    details?: Record<string, unknown>
    retryable?: boolean
    read: { notFound: boolean; unexpected: boolean }
    form: Expected
    dialog: Expected
  }

  const FIELD_ERRORS = { errors: [{ field: 'ttl_days', reason: 'range' }] }
  const alertError = (unexpected = false, target = 'dialog-alert'): Expected => ({
    target,
    variant: 'error',
    unexpected,
  })
  const formAlert = (unexpected = false): Expected => alertError(unexpected, 'form-alert')

  const ROWS: Row[] = [
    // ── Admin 固有 14 種
    {
      code: 'config_invalid',
      status: 400,
      details: { ...FIELD_ERRORS, crawler_message: 'root: x' },
      read: { notFound: false, unexpected: true },
      form: { target: 'field', variant: 'error', unexpected: false },
      dialog: alertError(),
    },
    {
      code: 'source_config_not_found',
      status: 404,
      read: { notFound: true, unexpected: false },
      form: formAlert(),
      dialog: alertError(),
    },
    {
      code: 'job_not_found',
      status: 404,
      read: { notFound: true, unexpected: false },
      form: formAlert(),
      dialog: alertError(),
    },
    {
      code: 'lock_held',
      status: 409,
      details: { lock_state: 'orphan' },
      read: { notFound: false, unexpected: true },
      form: { target: 'form-alert', variant: 'warning', unexpected: false },
      dialog: { target: 'dialog-alert', variant: 'warning', unexpected: false },
    },
    {
      code: 'lock_in_use',
      status: 409,
      details: { lock_state: 'lease_expired' },
      read: { notFound: false, unexpected: true },
      form: { target: 'form-alert', variant: 'warning', unexpected: false },
      dialog: { target: 'dialog-alert', variant: 'warning', unexpected: false },
    },
    {
      code: 'source_deleting',
      status: 409,
      read: { notFound: false, unexpected: true },
      form: formAlert(),
      dialog: alertError(),
    },
    {
      code: 'maintenance_enabled',
      status: 409,
      read: { notFound: false, unexpected: true },
      form: formAlert(),
      dialog: alertError(),
    },
    {
      code: 'source_already_exists',
      status: 409,
      details: { status: 'deleting' },
      read: { notFound: false, unexpected: true },
      form: { target: 'field', variant: 'error', unexpected: false },
      dialog: alertError(),
    },
    {
      code: 'job_not_cancellable',
      status: 409,
      read: { notFound: false, unexpected: true },
      form: formAlert(true),
      dialog: alertError(true),
    },
    {
      code: 'job_already_finished',
      status: 409,
      details: { status: 'failed' },
      read: { notFound: false, unexpected: true },
      form: { target: 'success', variant: 'info', unexpected: false },
      dialog: { target: 'success', variant: 'info', unexpected: false },
    },
    {
      code: 'crawler_error',
      status: 502,
      read: { notFound: false, unexpected: true },
      form: formAlert(true),
      dialog: alertError(true),
    },
    {
      code: 'crawler_unavailable',
      status: 503,
      retryable: true,
      read: { notFound: false, unexpected: true },
      form: formAlert(),
      dialog: alertError(),
    },
    {
      code: 'crawler_unreachable',
      status: 503,
      retryable: true,
      read: { notFound: false, unexpected: true },
      form: formAlert(),
      dialog: alertError(),
    },
    {
      code: 'crawler_response_lost',
      status: 504,
      details: { outcome_unknown: true },
      read: { notFound: false, unexpected: true },
      form: { target: 'form-alert', variant: 'warning', unexpected: false },
      dialog: { target: 'dialog-alert', variant: 'warning', unexpected: false },
    },
    // ── 共通 6 種
    {
      code: 'invalid_request',
      status: 400,
      details: FIELD_ERRORS,
      read: { notFound: true, unexpected: false },
      form: { target: 'field', variant: 'error', unexpected: false },
      // ダイアログ系は画面が送らない値の違反なので想定外
      dialog: alertError(true),
    },
    {
      code: 'not_found',
      status: 404,
      read: { notFound: true, unexpected: false },
      form: formAlert(true),
      dialog: alertError(true),
    },
    {
      code: 'method_not_allowed',
      status: 405,
      read: { notFound: false, unexpected: true },
      form: formAlert(true),
      dialog: alertError(true),
    },
    {
      code: 'http_error',
      status: 418,
      read: { notFound: false, unexpected: true },
      form: formAlert(true),
      dialog: alertError(true),
    },
    {
      code: 'internal_error',
      status: 500,
      read: { notFound: false, unexpected: true },
      form: formAlert(true),
      dialog: alertError(true),
    },
    {
      code: 'unavailable',
      status: 503,
      retryable: true,
      read: { notFound: false, unexpected: false },
      form: formAlert(true),
      dialog: alertError(true),
    },
  ]

  const input = (row: Row) =>
    apiError(row.code, {
      status: row.status,
      retryable: row.retryable ?? false,
      ...(row.details !== undefined && { details: row.details }),
    })

  it('表は 20 code を過不足なく持つ', () => {
    expect(ROWS.map((row) => row.code).sort()).toEqual(
      [...ADMIN_ERROR_CODES, ...COMMON_ERROR_CODES].sort(),
    )
  })

  it.each(ROWS)('$code: 読み取り', (row) => {
    expect(describeError(input(row), READ)).toMatchObject({
      target: 'state-block',
      notFound: row.read.notFound,
      unexpected: row.read.unexpected,
      outcomeUnknown: false,
      resendSafe: false,
    })
  })

  it.each(ROWS)('$code: フォーム(S3 の保存)', (row) => {
    const description = describeError(input(row), FORM)

    expect(description).toMatchObject({ ...row.form, notFound: false })
    // 結果不明(crawler_response_lost)だけが、保存系の「もう一度保存」(resendSafe)を持つ
    expect(description.resendSafe).toBe(row.code === 'crawler_response_lost')
    expect(description.outcomeUnknown).toBe(row.code === 'crawler_response_lost')
  })

  it.each(ROWS)('$code: ダイアログ(DLG-1 の起動)', (row) => {
    const description = describeError(input(row), DIALOG)

    expect(description).toMatchObject({ ...row.dialog, notFound: false })
    // ダイアログ系は「もう一度保存」を出さない(起動系は確認の導線)
    expect(description.resendSafe).toBe(false)
    expect(description.outcomeUnknown).toBe(row.code === 'crawler_response_lost')
  })

  it.each(ALL_WRITE_OPERATIONS)(
    'crawler_response_lost(api の JSON): %s の resendSafe は、保存系(registerSource・updateSource)だけ true',
    (operation) => {
      const description = describeError(
        apiError('crawler_response_lost', { status: 504, details: { outcome_unknown: true } }),
        { operation },
      )

      expect(description.outcomeUnknown).toBe(true)
      expect(description.retryable).toBe(false)
      expect(description.resendSafe).toBe(
        operation === 'registerSource' || operation === 'updateSource',
      )
    },
  )

  describe('未知の code', () => {
    it.each([
      ['読み取り', READ],
      ['フォーム', FORM],
      ['ダイアログ', DIALOG],
    ] as const)('%s: 想定外として扱い、診断に code と HTTP ステータスを出す', (_name, context) => {
      expect(describeError(apiError('brand_new_code', { status: 418 }), context)).toMatchObject({
        unexpected: true,
        notFound: false,
        diagnostic: { code: 'brand_new_code', status: 418 },
      })
    })

    it('書き込みの未知の code は、フォームでもダイアログでも消えないアラート(error)', () => {
      expect(describeError(apiError('brand_new_code'), FORM)).toMatchObject({
        target: 'form-alert',
        variant: 'error',
      })
      expect(describeError(apiError('brand_new_code'), DIALOG)).toMatchObject({
        target: 'dialog-alert',
        variant: 'error',
      })
    })
  })

  describe('details.outcome_unknown', () => {
    it('false のとき、結果不明の code(crawler_response_lost)は表の指定どおり結果不明のまま', () => {
      const description = describeError(
        apiError('crawler_response_lost', { status: 504, details: { outcome_unknown: false } }),
        DIALOG,
      )

      expect(description).toMatchObject({ outcomeUnknown: true, retryable: false })
    })

    it('false のとき、ほかの code は結果不明にならない', () => {
      const description = describeError(
        apiError('crawler_unavailable', {
          status: 503,
          retryable: true,
          details: { outcome_unknown: false },
        }),
        DIALOG,
      )

      expect(description).toMatchObject({ outcomeUnknown: false, retryable: true })
    })

    it('表にない code に outcome_unknown: true が付いたときは、結果不明(再試行を出さない)', () => {
      for (const context of [FORM, DIALOG]) {
        expect(
          describeError(
            apiError('brand_new_code', {
              status: 504,
              retryable: true,
              details: { outcome_unknown: true },
            }),
            context,
          ),
        ).toMatchObject({ outcomeUnknown: true, retryable: false, unexpected: true })
      }
    })

    it('outcome_unknown が true 以外の値(文字列・1)は結果不明にしない', () => {
      for (const value of ['true', 1, null]) {
        expect(
          describeError(
            apiError('crawler_unavailable', { status: 503, details: { outcome_unknown: value } }),
            DIALOG,
          ).outcomeUnknown,
        ).toBe(false)
      }
    })
  })
})

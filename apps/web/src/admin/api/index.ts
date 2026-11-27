// admin/api の公開口(F 3.3)。外(queries・tests など)はここだけを import する(R2)。
//
// - 生成型は**スキーマ名の型**だけを出す。`{Op}Response`・`{Op}Response2`(EP 側の型。`CancelJobResponse2` など)は出さない
//   (生成の命名が変わっても影響を受けない。`{Op}Data`・`{Op}Responses`・`{Op}Errors` は admin/api の中だけで使う)
// - 生成の `{fn}Options`・`{fn}Mutation` はそのまま出す(包むラッパーは作らない。エラーの正規化は client の interceptor)
// - SDK 関数(`listSources` など)・生成の `client`・`{fn}QueryKey` は出さない(Query・mutation 経由だけ。key は queries の key factory)
export {
  cancelJobMutation,
  getClusterOptions,
  getDashboardOptions,
  getJobOptions,
  getMetaOptions,
  getSourceOptions,
  listDocumentsOptions,
  listJobsOptions,
  listSourcesOptions,
  registerSourceMutation,
  releaseLockMutation,
  startCrawlMutation,
  startSourceDeleteMutation,
  updateSourceMutation,
} from './generated/@tanstack/vue-query.gen'

export type {
  CancelJobResponse,
  ClusterResponse,
  ClusterSummary,
  ComponentId,
  ComponentState,
  ComponentStatus,
  DashboardResponse,
  Deletion,
  DeletionConfirmation,
  DeletionCurrent,
  DeletionCurrentState,
  DeletionSettings,
  DeletionSummary,
  DocumentExistence,
  DocumentListResponse,
  DocumentTab,
  ErrorBody,
  ErrorDetails,
  ErrorResponse,
  ExistingJob,
  ExtractFailedDocument,
  FieldError,
  IndexEntry,
  IndexSummary,
  JobAccepted,
  JobBrief,
  JobDetailResponse,
  JobListItem,
  JobListResponse,
  JobStatus,
  JobTrigger,
  JobType,
  Lock,
  LockState,
  MetaResponse,
  NodeEntry,
  OversizeDetector,
  OversizeDocument,
  Reason,
  RegisterSourceBody,
  Registration,
  RegistrationPhase,
  ReleaseLockResponse,
  RequestedOptions,
  RerunBlockedReason,
  ShardEntry,
  SkippedDocument,
  SkipStage,
  SourceDetailResponse,
  SourceListItem,
  SourceListResponse,
  SourceSettings,
  SourceStatus,
  StartCrawlBody,
  SummaryPendingDocument,
  TabCounts,
  Unavailable,
  UnavailableReason,
  UpdateSourceBody,
} from './generated/types.gen'

export { configureApiClient } from './client'
export { describeError } from './errors/describeError'
export type {
  DisplayTarget,
  ErrorContext,
  ErrorDescription,
  FieldErrorEntry,
  WriteOperation,
} from './errors/describeError'
export type { AlertVariant } from './errors/errorTable'
export { isValidPathId } from './pathParams'
export { isApiError } from '@/shared/api/apiError'
export type { ApiError } from '@/shared/api/apiError'

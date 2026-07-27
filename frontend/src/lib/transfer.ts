import { computed } from 'vue'
import { apiGet, apiPost } from './bridge'
import { BusinessError, Unauthorized } from './errors'
import { t } from './i18n'

export interface ReadyServer { server_id: string; name: string }
export interface Binding { umo: string; server_ids: string[] }
export interface AllowedGroup { umo: string; note: string }

// 预览端点回传（restarting 时仅 ok+restarting；否则按 target 带 bindings 或 allowed_groups）。
export interface TransferPreview {
  ok: boolean
  restarting?: boolean
  ready_servers?: ReadyServer[]
  bindings?: Binding[] // target=single（multi→single）
  allowed_groups?: AllowedGroup[] // target=multi（single→multi）
}

export interface TransferBody {
  target_mode: 'single' | 'multi'
  surviving_server_id?: string
  migrate_umos: string[]
  purge_others: boolean
}

export interface TransferWarnings {
  cleared_group_servers?: false // 源介质清理未尽（M-f）
  purge_failed?: string[] // 部分台数据清理失败
}

export interface TransferSummary {
  from: string
  to: string
  surviving: string | null
  migrated: number
  purged: Record<string, Record<string, number>>
  failed_server_ids: string[]
}

// postTransfer 只在 ok:true 返回（ok:false 已由 bridge 抛 BusinessError）。
export interface TransferResult {
  ok: true
  config: Record<string, unknown>
  warnings: TransferWarnings
  summary: TransferSummary
}

export interface OrphanList { ok: boolean; orphans: string[]; restarting?: boolean }
export interface OrphanPurgeResult {
  ok: true
  purged: Record<string, Record<string, number>>
  rejected: string[]
  failed_server_ids: string[]
}

export function previewTransfer(target: 'single' | 'multi'): Promise<TransferPreview> {
  return apiGet<TransferPreview>('mode/transfer/preview?target=' + encodeURIComponent(target))
}

export function postTransfer(body: TransferBody): Promise<TransferResult> {
  return apiPost<TransferResult>('mode/transfer', body)
}

export function listOrphans(): Promise<OrphanList> {
  return apiGet<OrphanList>('mode/orphans')
}

// 不传 server_ids（undefined）：后端持锁现场重算孤儿集、清全部当前孤儿（不信客户端，Blocker-O）。
// 显式数组（含空 []）：原样透传，与后端 FIX1 对齐（空数组=清 nothing，undefined=清全部）。
export function purgeOrphans(serverIds?: string[]): Promise<OrphanPurgeResult> {
  const body = serverIds === undefined ? {} : { server_ids: serverIds }
  return apiPost<OrphanPurgeResult>('mode/orphans/purge', body)
}

export const TRANSFER_ERR = computed<Record<string, string>>(() => Object.fromEntries([
  'transfer_in_progress', 'purge_in_progress', 'busy', 'no_change', 'invalid_target',
  'invalid_surviving', 'no_ready_server', 'no_ready_target', 'invalid_migrate_umos',
  'too_many_groups', 'migrate_bind_failed', 'restart_failed_rolled_back', 'restart_failed',
].map((code) => [code, t(`err.transfer.${code}`)])))

// 统一错误文案：Unauthorized / BusinessError 码表 / 兜底。模式不变路径只弹此文案、不改 state。
export function mapTransferError(e: unknown): string {
  if (e instanceof Unauthorized) return t('err.unauthorized')
  if (e instanceof BusinessError) return TRANSFER_ERR.value[e.code] ?? t('err.transfer.fallback')
  return t('err.transfer.fallback')
}

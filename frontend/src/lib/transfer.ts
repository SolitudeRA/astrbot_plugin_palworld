import { apiGet, apiPost } from './bridge'
import { BusinessError, Unauthorized } from './errors'

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

// 不传 server_ids：后端持锁现场重算孤儿集、清全部当前孤儿（不信客户端，Blocker-O）。
export function purgeOrphans(serverIds?: string[]): Promise<OrphanPurgeResult> {
  const body = serverIds && serverIds.length ? { server_ids: serverIds } : {}
  return apiPost<OrphanPurgeResult>('mode/orphans/purge', body)
}

export const TRANSFER_ERR: Record<string, string> = {
  transfer_in_progress: '转移正在进行中，请稍候',
  purge_in_progress: '清理正在进行中，请稍候',
  busy: '系统忙（重载中），请稍后再试',
  no_change: '目标模式与当前一致，无需切换',
  invalid_target: '切换目标无效',
  invalid_surviving: '所选保留服务器无效或未就绪',
  no_ready_server: '没有就绪的服务器，无法切换到单服务器模式',
  no_ready_target: '没有就绪的服务器可绑定，无法迁移授权',
  invalid_migrate_umos: '迁移列表已过期，请重新打开切换向导后重试',
  too_many_groups: '授权群数量超过上限（200），无法迁移，请先精简名单',
  migrate_bind_failed: '授权预绑定失败，模式未改变，可稍后重试',
  restart_failed_rolled_back: '切换未生效，已恢复原模式',
  restart_failed: '切换未生效且恢复失败，请检查后台日志',
}

// 统一错误文案：Unauthorized / BusinessError 码表 / 兜底。模式不变路径只弹此文案、不改 state。
export function mapTransferError(e: unknown): string {
  if (e instanceof Unauthorized) return '未登录或登录已过期，请重新登录 Dashboard'
  if (e instanceof BusinessError) return TRANSFER_ERR[e.code] ?? '操作失败，请重试'
  return '操作失败，请重试'
}

import { BridgeMissing } from './errors'

// 不回显原始错误文本（避免泄露内部信息）
export function bootMessage(err: unknown): string {
  return err instanceof BridgeMissing ? '需要 AstrBot ≥ v4.24.1 的插件页面环境' : '初始化失败，请刷新'
}

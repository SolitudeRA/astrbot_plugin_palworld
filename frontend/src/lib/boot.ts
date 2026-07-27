import { BridgeMissing } from './errors'
import { t } from './i18n'

// 不回显原始错误文本（避免泄露内部信息）
export function bootMessage(err: unknown): string {
  return err instanceof BridgeMissing ? t('app.boot.bridge_missing') : t('app.boot.failed')
}

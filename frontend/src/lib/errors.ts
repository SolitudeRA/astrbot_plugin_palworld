export class BridgeMissing extends Error {
  constructor() { super('AstrBotPluginPage bridge 不存在'); this.name = 'BridgeMissing' }
}
export class Unauthorized extends Error {
  constructor() { super('未登录或登录已过期'); this.name = 'Unauthorized' }
}
export class BusinessError extends Error {
  code: string; path?: string
  constructor(code: string, path?: string) {
    super(`业务错误: ${code}`); this.name = 'BusinessError'; this.code = code; this.path = path
  }
}
export class RequestFailed extends Error {
  constructor(message = '请求失败') { super(message); this.name = 'RequestFailed' }
}

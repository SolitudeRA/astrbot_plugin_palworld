export {}
declare global {
  interface AstrBotBridge {
    ready(): Promise<void>
    apiGet(path: string): Promise<any>
    apiPost(path: string, body?: unknown): Promise<any>
  }
  interface Window { AstrBotPluginPage?: AstrBotBridge }
}

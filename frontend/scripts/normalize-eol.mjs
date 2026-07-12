// 构建产物统一 LF 行尾。
// 背景：Vite/rollup 在 Windows 上会给生成的 pages/settings/index.html 写 CRLF，
// 而仓库 .gitattributes 规定 `pages/settings/** text eol=lf`（强制 LF）。二者冲突
// 会让每次 Windows 构建后工作区显示该产物「已修改」（纯行尾的幻影 diff），甚至在
// 有未提交产物时阻塞 git pull/merge（曾踩坑）。此步在 `vite build` 后把产物统一成
// LF，保证工作副本与仓库(LF)逐字节一致、构建后永不因行尾变脏，且跨平台确定性一致。
import { readdirSync, readFileSync, writeFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath, URL } from 'node:url'

// 本脚本在 frontend/scripts/ 下；产物在仓库根 pages/settings/（vite outDir ../pages/settings）。
const outDir = fileURLToPath(new URL('../../pages/settings', import.meta.url))
const EXTS = new Set(['.html', '.css', '.js', '.map', '.json'])

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) { walk(p); continue }
    const dot = name.lastIndexOf('.')
    if (dot < 0 || !EXTS.has(name.slice(dot))) continue
    const text = readFileSync(p, 'utf8')
    if (text.includes('\r\n')) {
      writeFileSync(p, text.replace(/\r\n/g, '\n'))
      console.log('normalized LF:', name)
    }
  }
}

walk(outDir)

import { readdirSync, readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

// 基于脚本自身位置解析，cwd 无关：脚本在 <root>/frontend/scripts/，产物在 <root>/pages/settings/assets/。
// 使从仓库根（CI）与 frontend/ 下（本地）跑均可，不依赖当前工作目录。
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
const dir = join(repoRoot, 'pages/settings/assets')
const files = readdirSync(dir)
const js = files.filter((f) => f.endsWith('.js'))
const css = files.filter((f) => f.endsWith('.css'))
const fail = (m) => { console.error('FAIL:', m); process.exit(1) }

if (js.length !== 1) fail(`expected exactly 1 .js, found ${js.length}: ${js.join(', ')}`)
if (css.length > 1) fail(`expected at most 1 .css, found ${css.length}: ${css.join(', ')}`)

const src = readFileSync(join(dir, js[0]), 'utf8')
const banned = ['}from"./', "}from'./", '*from"./', ' from"./', 'import(']
for (const needle of banned) {
  if (src.includes(needle)) fail(`bundle ${js[0]} contains banned token: ${JSON.stringify(needle)}`)
}
console.log(`OK: single-file bundle verified -> ${join(dir, js[0])}`)

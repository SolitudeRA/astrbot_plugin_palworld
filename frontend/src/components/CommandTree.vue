<script setup lang="ts">
import { computed, ref } from 'vue'
import { PAL_TREE, GROUP_LABELS, type PalTreeNode, type Tri } from '../lib/schema'
import type { CmdPerm } from '../lib/collect'

const props = defineProps<{ modelValue: Record<string, CmdPerm>; hideGroups?: string[] }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, CmdPerm>]; change: [] }>()

type Axis = 'enabled' | 'admin_only'
const ENABLE_OPTS: { v: Tri; t: string }[] = [
  { v: 'inherit', t: '默认' }, { v: 'on', t: '开' }, { v: 'off', t: '关' },
]
const ADMIN_OPTS: { v: Tri; t: string }[] = [
  { v: 'inherit', t: '默认' }, { v: 'on', t: '仅管理' }, { v: 'off', t: '所有人' },
]

// 分组：按 PAL_TREE 中出现顺序收集组（world/guild/player/server/link），扁平命令归「其他」
interface Grp { key: string; label: string; nodes: PalTreeNode[]; isFlat: boolean }
const groups = computed<Grp[]>(() => {
  const order: string[] = []
  const byKey: Record<string, PalTreeNode[]> = {}
  for (const n of PAL_TREE) {
    if ((props.hideGroups ?? []).includes(n.group ?? '')) continue
    const k = n.group ?? '__flat__'
    if (!(k in byKey)) { byKey[k] = []; order.push(k) }
    byKey[k].push(n)
  }
  return order.map((k) => ({
    key: k,
    label: k === '__flat__' ? '其他' : (GROUP_LABELS[k] ?? k),
    nodes: byKey[k],
    isFlat: k === '__flat__',
  }))
})

// 组头批量：整组某轴是否可配（组内任一子命令该轴可配才有意义，否则组头格显「—」）
const groupEnableConfigurable = (g: Grp) => g.nodes.some((n) => n.enableConfigurable)
const groupAdminConfigurable = (g: Grp) => g.nodes.some((n) => n.adminConfigurable && !n.adminForced)

const expanded = ref<Record<string, boolean>>(
  Object.fromEntries(PAL_TREE.map((n) => [n.group ?? '__flat__', true])),
)
const toggleGroup = (k: string) => { expanded.value[k] = !expanded.value[k] }

const cellOf = (command: string, axis: Axis): Tri => props.modelValue[command]?.[axis] ?? 'inherit'

function setCell(command: string, axis: Axis, v: Tri) {
  const cur: CmdPerm = props.modelValue[command] ?? { enabled: 'inherit', admin_only: 'inherit' }
  const next = { ...props.modelValue, [command]: { ...cur, [axis]: v } }
  emit('update:modelValue', next)
  emit('change')
}

// 叶子 enable 格：enableConfigurable=false → 恒开（核心命令，内置锁定）
// 叶子 admin 格：adminForced=true → 恒「仅管理员」；adminConfigurable=false 且非 forced → 恒「所有人」
function lockedLabel(n: PalTreeNode, axis: Axis): string | null {
  if (axis === 'enabled') return n.enableConfigurable ? null : '开'
  if (n.adminForced) return '仅管理员'
  if (!n.adminConfigurable) return '所有人'
  return null
}
const optsOf = (axis: Axis) => (axis === 'enabled' ? ENABLE_OPTS : ADMIN_OPTS)
</script>

<template>
  <div class="cmdtree">
    <div class="ct-legend">
      <span class="t">命令权限</span>
      <span class="c">按组批量或逐条设置「是否启用 / 是否仅管理员」；<b>默认</b>=继承内置，<b>开/关</b>为显式覆盖。内置锁定的格不可改。</span>
    </div>

    <div v-for="g in groups" :key="g.key" class="ct-group">
      <!-- 组头行 -->
      <div class="ct-row ct-grouphead">
        <button type="button" class="ct-gname" :aria-expanded="expanded[g.key]" @click="toggleGroup(g.key)">
          <span class="chev" :class="{ open: expanded[g.key] }">▸</span>{{ g.label }}
        </button>
        <div class="ct-cells">
          <!-- 扁平段无组名可写，不渲染批量格；有组的写组名行 -->
          <template v-if="!g.isFlat">
            <div class="ct-cell">
              <template v-if="groupEnableConfigurable(g)">
                <button v-for="o in ENABLE_OPTS" :key="o.v" type="button" class="seg"
                  :class="{ sel: cellOf(g.key, 'enabled') === o.v, act: o.v !== 'inherit' && cellOf(g.key, 'enabled') === o.v }"
                  @click="setCell(g.key, 'enabled', o.v)">{{ o.t }}</button>
              </template>
              <span v-else class="ct-na">—</span>
            </div>
            <div class="ct-cell">
              <template v-if="groupAdminConfigurable(g)">
                <button v-for="o in ADMIN_OPTS" :key="o.v" type="button" class="seg"
                  :class="{ sel: cellOf(g.key, 'admin_only') === o.v, act: o.v !== 'inherit' && cellOf(g.key, 'admin_only') === o.v }"
                  @click="setCell(g.key, 'admin_only', o.v)">{{ o.t }}</button>
              </template>
              <span v-else class="ct-na">—</span>
            </div>
          </template>
          <template v-else>
            <div class="ct-cell"><span class="ct-colh">启用</span></div>
            <div class="ct-cell"><span class="ct-colh">仅管理员</span></div>
          </template>
        </div>
      </div>

      <!-- 叶子行 -->
      <template v-if="expanded[g.key]">
        <div v-for="n in g.nodes" :key="n.path" class="ct-row ct-leaf" :class="{ danger: n.danger }">
          <div class="ct-lname">
            <span class="lbl">{{ n.label }}<span v-if="n.danger" class="dtag">危险</span></span>
            <span class="path mono">/pal {{ n.path }}</span>
          </div>
          <div class="ct-cells">
            <div v-for="axis in (['enabled', 'admin_only'] as const)" :key="axis" class="ct-cell">
              <span v-if="lockedLabel(n, axis)" class="ct-lock">{{ lockedLabel(n, axis) }}<small>内置</small></span>
              <template v-else>
                <button v-for="o in optsOf(axis)" :key="o.v" type="button" class="seg"
                  :class="{ sel: cellOf(n.path, axis) === o.v, act: o.v !== 'inherit' && cellOf(n.path, axis) === o.v }"
                  @click="setCell(n.path, axis, o.v)">{{ o.t }}</button>
              </template>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.cmdtree { display: flex; flex-direction: column; gap: 10px; }
.ct-legend { display: flex; flex-direction: column; gap: 3px; padding: 0 2px 2px; }
.ct-legend .t { font-size: 13px; font-weight: 600; color: var(--ink); }
.ct-legend .c { font-size: 12px; color: var(--ink-2); line-height: 1.5; }
.ct-legend b { color: var(--ink); font-weight: 600; }

.ct-group { border: 1px solid var(--rule); border-radius: var(--r); overflow: hidden; background: var(--card); }
.ct-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; }
.ct-grouphead { background: var(--sink); border-bottom: 1px solid var(--rule); }
.ct-gname { flex: 1; display: flex; align-items: center; gap: 7px; font-family: var(--sans); font-size: 13px; font-weight: 600; color: var(--ink); background: none; border: none; cursor: pointer; text-align: left; padding: 0; }
.ct-gname .chev { display: inline-block; font-size: 10px; color: var(--ink-3); transition: transform .15s; }
.ct-gname .chev.open { transform: rotate(90deg); }
.ct-gname:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: 4px; }

.ct-leaf { border-top: 1px solid var(--rule-2); }
.ct-leaf.danger { background: color-mix(in srgb, var(--warn) 6%, var(--card)); }
.ct-lname { flex: 1; display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ct-lname .lbl { font-size: 12.5px; color: var(--ink); display: flex; align-items: center; gap: 6px; }
.ct-lname .path { font-size: 11px; color: var(--ink-3); }
.dtag { font-size: 10px; font-weight: 600; color: var(--on-warn, #fff); background: var(--warn); border-radius: 4px; padding: 1px 5px; }

.ct-cells { display: flex; gap: 8px; flex: none; }
.ct-cell { width: 168px; display: flex; align-items: center; justify-content: flex-end; gap: 0; }
.ct-colh { font-size: 11px; color: var(--ink-3); font-weight: 600; width: 100%; text-align: center; }
.ct-na { color: var(--ink-3); font-size: 12px; }

.seg { font-family: var(--sans); font-size: 11.5px; color: var(--ink-2); background: var(--card); border: 1px solid var(--rule-2); padding: 4px 9px; cursor: pointer; transition: background .12s, color .12s, border-color .12s; }
.seg:first-child { border-radius: 7px 0 0 7px; }
.seg:last-child { border-radius: 0 7px 7px 0; }
.seg + .seg { border-left: none; }
.seg:hover { color: var(--ink); }
.seg:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; position: relative; z-index: 1; }
.seg.sel { color: var(--ink); background: var(--sink); font-weight: 600; }
.seg.act { color: var(--on-amber); background: var(--amber); border-color: var(--amber); }

.ct-lock { display: inline-flex; align-items: baseline; gap: 4px; font-size: 11.5px; color: var(--ink-3); font-style: normal; }
.ct-lock small { font-size: 9.5px; color: var(--ink-3); opacity: .75; border: 1px solid var(--rule-2); border-radius: 4px; padding: 0 3px; }
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { SwitchRoot, SwitchThumb } from 'reka-ui'
import { PAL_TREE, GROUP_LABELS, type PalTreeNode, type Tri } from '../lib/schema'
import type { CmdPerm } from '../lib/collect'
import { cellOf as libCellOf, inheritAdmin as libInheritAdmin, effAdmin as libEffAdmin, writeAxis } from '../lib/permissions'

// 管理员限制表（单轴）：功能启停已拆去「功能」页，本组件只管 admin_only 轴。
// 只列可锁命令（adminConfigurable 且非 forced，15 条）；恒仅管理员/恒所有人的收进表尾说明。
const props = defineProps<{ modelValue: Record<string, CmdPerm>; hideGroups?: string[] }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, CmdPerm>]; change: [] }>()

interface Grp { key: string; label: string; nodes: PalTreeNode[]; isFlat: boolean }
const groups = computed<Grp[]>(() => {
  const order: string[] = []
  const byKey: Record<string, PalTreeNode[]> = {}
  for (const n of PAL_TREE) {
    if ((props.hideGroups ?? []).includes(n.group ?? '')) continue
    if (!(n.adminConfigurable && !n.adminForced)) continue // 单轴：只列可锁叶子
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

const expanded = ref<Record<string, boolean>>(
  Object.fromEntries(PAL_TREE.map((n) => [n.group ?? '__flat__', true])),
)
const toggleGroup = (k: string) => { expanded.value[k] = !expanded.value[k] }

// 单轴覆盖判定：只认 admin_only（enabled 覆盖归「功能」页管辖，这里不亮标、不清除）
const adminCell = (command: string): Tri => libCellOf(props.modelValue, command, 'admin_only')
const hasAdminOverride = (command: string): boolean => adminCell(command) !== 'inherit'
const effAdmin = (n: PalTreeNode) => libEffAdmin(props.modelValue, n)
const inheritAdmin = (n: PalTreeNode) => libInheritAdmin(props.modelValue, n)
// 组头开关生效值：组 admin 覆盖 ?? 内置（所有人=false）
const groupEff = (g: Grp): boolean => {
  const v = adminCell(g.key)
  return v === 'inherit' ? false : v === 'on'
}
const groupManaged = (g: Grp) => !g.isFlat && hasAdminOverride(g.key)

// 写操作：目标 == 继承生效值 → 自动回归 inherit（不留冗余覆盖）
function write(command: string, v: Tri) {
  emit('update:modelValue', writeAxis(props.modelValue, command, 'admin_only', v))
  emit('change')
}
function onLeafToggle(n: PalTreeNode, target: boolean) {
  write(n.path, target === inheritAdmin(n) ? 'inherit' : (target ? 'on' : 'off'))
}
function onGroupToggle(g: Grp, target: boolean) {
  write(g.key, target === false ? 'inherit' : 'on') // 组内置=所有人（false）
}
// ↺ 恢复：只清 admin 轴（不碰功能页的 enabled 覆盖）
const resetAdmin = (command: string) => write(command, 'inherit')

// 表尾说明：forced（恒仅管理员）与恒所有人的收拢；单模式隐藏 link 时不提授权命令
const lockedNote = computed(() => {
  const hideLink = (props.hideGroups ?? []).includes('link')
  const forced = hideLink
    ? '服务器管控 7 条与「确认执行」恒需管理员'
    : '服务器管控 7 条、服务器授权 2 条与「确认执行」恒需管理员'
  const open = hideLink
    ? '帮助 / 我的账号标识 / 本群标识恒对所有人开放'
    : '服务器列表 / 帮助 / 我的账号标识 / 本群标识恒对所有人开放'
  return `${forced}；${open}。均为内置规则，不可更改。`
})
</script>

<template>
  <div class="cmdtree">
    <div class="ct-board">
      <!-- 列头（恒显）。开关：开=仅管理员，关=所有人 -->
      <div class="ct-row ct-colhead">
        <span class="ct-namecol">命令</span>
        <div class="ct-cell"><span class="ct-colh">仅管理员</span></div>
        <span class="ct-resetcol"></span>
      </div>

      <div v-for="g in groups" :key="g.key" class="ct-group">
        <!-- 组头行：整组批量。受管态 = amber 淡底 + 左竖条 + 「整组」标 -->
        <div class="ct-row ct-grouphead" :class="{ managed: groupManaged(g) }">
          <button type="button" class="ct-gname" :aria-expanded="expanded[g.key]" @click="toggleGroup(g.key)">
            <span class="chev" :class="{ open: expanded[g.key] }">▸</span>{{ g.label }}
            <span v-if="groupManaged(g)" class="grp-tag">整组</span>
          </button>
          <div class="ct-cell">
            <SwitchRoot v-if="!g.isFlat" class="pw-switch sm" :class="{ ovr: hasAdminOverride(g.key) }"
              :model-value="groupEff(g)" :aria-label="g.label + ' 整组仅管理员'"
              @update:model-value="(v: boolean) => onGroupToggle(g, v)">
              <SwitchThumb class="pw-switch-thumb" />
            </SwitchRoot>
          </div>
          <span class="ct-resetcol">
            <button v-if="groupManaged(g)" type="button" class="ct-reset" aria-label="恢复整组默认"
              title="恢复整组默认" @click.stop="resetAdmin(g.key)">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
            </button>
          </span>
        </div>

        <!-- 叶子行：开关显示生效值；单独设置 = 名旁圆点 + amber 环 + ↺ -->
        <template v-if="expanded[g.key]">
          <div v-for="n in g.nodes" :key="n.path" class="ct-row ct-leaf"
            :class="{ grouped: groupManaged(g) && !hasAdminOverride(n.path) }">
            <div class="ct-lname">
              <span class="lbl">{{ n.label }}
                <span v-if="hasAdminOverride(n.path)" class="ov-dot" title="此命令已单独设置" aria-label="已单独设置"></span>
              </span>
              <span class="path mono">/pal {{ n.path }}</span>
            </div>
            <div class="ct-cell">
              <SwitchRoot class="pw-switch sm" :class="{ ovr: hasAdminOverride(n.path) }"
                :model-value="effAdmin(n)" :aria-label="n.label + ' 仅管理员'"
                @update:model-value="(v: boolean) => onLeafToggle(n, v)">
                <SwitchThumb class="pw-switch-thumb" />
              </SwitchRoot>
            </div>
            <span class="ct-resetcol">
              <button v-if="hasAdminOverride(n.path)" type="button" class="ct-reset" aria-label="恢复跟随"
                title="恢复跟随（清除单独设置）" @click.stop="resetAdmin(n.path)">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
              </button>
            </span>
          </div>
        </template>
      </div>

      <!-- 内置规则收拢说明（原 10+4 条锁定行不再占行） -->
      <div class="ct-row ct-note">{{ lockedNote }}</div>
    </div>
  </div>
</template>

<style scoped>
/* 连续观测面：单一外框，组头分隔行，叶子 dashed 分隔 */
.cmdtree { display: flex; flex-direction: column; }
.ct-board { border: 1px solid var(--rule); border-radius: var(--r); overflow: hidden; background: var(--card); }
.ct-row { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-2) var(--space-3); }

.ct-colhead { background: linear-gradient(var(--raise), var(--card)); border-bottom: 1px solid var(--rule-2); }
.ct-namecol { flex: 1; font-size: var(--fs-caption); color: var(--ink-2); font-weight: var(--fw-semibold); letter-spacing: var(--track-eyebrow); }
.ct-colh { font-size: var(--fs-caption); color: var(--ink-2); font-weight: var(--fw-semibold); letter-spacing: var(--track-eyebrow); width: 100%; text-align: right; }

.ct-grouphead { background: var(--sink); border-top: 1px solid var(--rule); }
.ct-group:first-of-type .ct-grouphead { border-top: none; }
/* 受管态（整组批量生效中）：amber 淡底 + 左竖条（Unity override bar / GitHub managed 语义） */
.ct-grouphead.managed { background: color-mix(in srgb, var(--amber) 9%, var(--sink)); box-shadow: inset 3px 0 0 var(--amber); }
.ct-gname { flex: 1; display: flex; align-items: center; gap: var(--space-2); font-family: var(--sans); font-size: var(--fs-sm); font-weight: var(--fw-semibold); color: var(--ink); background: none; border: none; cursor: pointer; text-align: left; padding: 0; }
.ct-gname .chev { display: inline-block; font-size: var(--fs-caption); color: var(--ink-3); transition: transform var(--motion-fast); }
.ct-gname .chev.open { transform: rotate(90deg); }
.ct-gname:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: var(--r-sm); }
.grp-tag { font-size: var(--fs-caption); font-weight: var(--fw-medium); color: var(--amber); border: 1px solid color-mix(in srgb, var(--amber) 45%, transparent); background: color-mix(in srgb, var(--amber) 8%, transparent); border-radius: var(--r-pill); padding: 0 var(--space-2); }

.ct-leaf { border-top: 1px dashed var(--rule); }
/* 随组叶子：淡一档 amber 左竖条贯穿受管区块（单独设置的行不加——例外由圆点/环表达） */
.ct-leaf.grouped { box-shadow: inset 3px 0 0 color-mix(in srgb, var(--amber) 40%, transparent); }
.ct-lname { flex: 1; display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ct-lname .lbl { font-size: var(--fs-caption); color: var(--ink); display: flex; align-items: center; gap: var(--space-2); }
.ct-lname .path { font-size: var(--fs-caption); color: var(--ink-3); }
/* 单独设置标识：amber 圆点（行名旁）+ 开关 amber 外环 */
.ov-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--amber); flex: 0 0 auto; }
.pw-switch.ovr { box-shadow: 0 0 0 2px color-mix(in srgb, var(--amber) 55%, transparent); }

.ct-cell { width: 120px; display: flex; align-items: center; justify-content: flex-end; flex: none; }
.ct-resetcol { width: 36px; display: flex; justify-content: flex-end; flex: none; }
.ct-reset { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; color: var(--ink-3); background: none; border: 1px solid transparent; border-radius: var(--r-sm); padding: 0; cursor: pointer; transition: color var(--motion-fast), border-color var(--motion-fast), background var(--motion-fast); }
.ct-reset svg { width: 14px; height: 14px; display: block; }
.ct-reset:hover { color: var(--amber); border-color: color-mix(in srgb, var(--amber) 45%, transparent); background: color-mix(in srgb, var(--amber) 8%, transparent); }
.ct-reset:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }

.ct-note { border-top: 1px solid var(--rule); background: var(--sink); font-size: var(--fs-caption); color: var(--ink-3); line-height: var(--lh-snug); }
</style>

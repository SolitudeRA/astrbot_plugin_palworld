<script setup lang="ts">
import { computed, ref } from 'vue'
import { SwitchRoot, SwitchThumb } from 'reka-ui'
import { PAL_TREE, GROUP_LABELS, type PalTreeNode, type Tri } from '../lib/schema'
import type { CmdPerm } from '../lib/collect'
import {
  GROUP_DEFAULT_ENABLED, type Axis,
  cellOf as libCellOf,
  inheritEnabled as libInheritEnabled, effEnabled as libEffEnabled,
  inheritAdmin as libInheritAdmin, effAdmin as libEffAdmin,
  writeAxis,
} from '../lib/permissions'

// 单轴命令树（功能页与权限章复用同一组件，各挂一轴的实例）：
//   axis="enabled"    —— 功能启停：列 enableConfigurable 的 17 条；danger 不随组（F2）
//   axis="admin_only" —— 管理员限制：列可锁非 forced 的 15 条
// 交互同套：组头开关整组批量 + 叶子开关逐条精细 + 受管视觉（整组标/amber 竖条/圆点/↺）。
// 覆盖判定与 ↺ 只认本轴——两章各管一轴，绝不误伤对方轴的覆盖。
const props = defineProps<{ modelValue: Record<string, CmdPerm>; axis: Axis; hideGroups?: string[]; hidePaths?: string[] }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, CmdPerm>]; change: [] }>()

const isEnabledAxis = computed(() => props.axis === 'enabled')
// 本轴可配（不可配的行不消失，显示锁定文本——两页看到同一棵完整命令树）
const configurable = (n: PalTreeNode) =>
  props.axis === 'enabled' ? n.enableConfigurable : (n.adminConfigurable && !n.adminForced)
// 本轴锁定文本：enabled 恒开；admin forced 仅管理员、不可锁所有人
function lockedLabel(n: PalTreeNode): string | null {
  if (configurable(n)) return null
  if (props.axis === 'enabled') return '恒开'
  return n.adminForced ? '仅管理员' : '所有人'
}

interface Grp { key: string; label: string; nodes: PalTreeNode[]; isFlat: boolean }
const groups = computed<Grp[]>(() => {
  const order: string[] = []
  const byKey: Record<string, PalTreeNode[]> = {}
  for (const n of PAL_TREE) {
    if ((props.hideGroups ?? []).includes(n.group ?? '')) continue
    if ((props.hidePaths ?? []).includes(n.path)) continue // 功能页危险区承载的命令，树中不渲染
    // 权限页只列当前启用的命令：功能关着谈不上「谁可用」（功能页开启后即时出现）
    if (props.axis === 'admin_only' && !libEffEnabled(props.modelValue, n)) continue
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
// 组头批量开关：组内存在本轴可配叶子才有意义
const groupConfigurable = (g: Grp) => g.nodes.some((n) => configurable(n))

// 权限页 server 组默认收折（7 条全锁定，平时无需铺开）；功能页全展开（危险命令已拆去危险区）
const expanded = ref<Record<string, boolean>>(
  Object.fromEntries(PAL_TREE.map((n) => {
    const k = n.group ?? '__flat__'
    return [k, props.axis === 'enabled' || k !== 'server']
  })),
)
const toggleGroup = (k: string) => { expanded.value[k] = !expanded.value[k] }

// 本轴覆盖判定（另一轴的覆盖归另一页管辖，不亮标、不清除）
const axisCell = (command: string): Tri => libCellOf(props.modelValue, command, props.axis)
const hasAxisOverride = (command: string): boolean => axisCell(command) !== 'inherit'
const effOf = (n: PalTreeNode) =>
  props.axis === 'enabled' ? libEffEnabled(props.modelValue, n) : libEffAdmin(props.modelValue, n)
const inheritOf = (n: PalTreeNode) =>
  props.axis === 'enabled' ? libInheritEnabled(props.modelValue, n) : libInheritAdmin(props.modelValue, n)
// 组头开关生效值：组覆盖 ?? 组内置默认（enabled 按 FEATURE_DEFAULTS；admin 内置=所有人）
const groupDefault = (g: Grp): boolean =>
  props.axis === 'enabled' ? (GROUP_DEFAULT_ENABLED[g.key] ?? false) : false
const groupEff = (g: Grp): boolean => {
  const v = axisCell(g.key)
  return v === 'inherit' ? groupDefault(g) : v === 'on'
}
const groupManaged = (g: Grp) => !g.isFlat && hasAxisOverride(g.key)
// 组内本轴被单独设置的叶子数——「整组」标的诚实后缀 / 组未管时的弱化计数
const overriddenLeaves = (g: Grp) =>
  g.nodes.filter((n) => configurable(n) && hasAxisOverride(n.path)).length

// 写操作：目标 == 继承生效值 → 自动回归 inherit（不留冗余覆盖）
function write(command: string, v: Tri) {
  emit('update:modelValue', writeAxis(props.modelValue, command, props.axis, v))
  emit('change')
}
function onLeafToggle(n: PalTreeNode, target: boolean) {
  write(n.path, target === inheritOf(n) ? 'inherit' : (target ? 'on' : 'off'))
}
// 组头开关 = 「这组我统一管」：先收编组内叶子的本轴覆盖再写组键，不留残余例外。
// enabled 轴跳过 danger 叶子——F2 它们不归组管，其自设不该被整组操作扫掉。
function onGroupToggle(g: Grp, target: boolean) {
  let next = { ...props.modelValue }
  for (const n of g.nodes) {
    if (!configurable(n)) continue
    if (isEnabledAxis.value && n.danger) continue
    next = writeAxis(next, n.path, props.axis, 'inherit')
  }
  const v: Tri = target === groupDefault(g) ? 'inherit' : (target ? 'on' : 'off')
  emit('update:modelValue', writeAxis(next, g.key, props.axis, v))
  emit('change')
}

const colHead = computed(() => (isEnabledAxis.value ? '启用' : '仅管理员'))
</script>

<template>
  <div class="cmdtree">
    <div class="ct-board">
      <!-- 列头（恒显）。enabled：开=可用；admin_only：开=仅管理员 -->
      <div class="ct-row ct-colhead">
        <span class="ct-namecol">命令</span>
        <div class="ct-cell"><span class="ct-colh">{{ colHead }}</span></div>
      </div>

      <div v-for="g in groups" :key="g.key" class="ct-group"
        :class="{ mixed: groupManaged(g) && overriddenLeaves(g) > 0 }">
        <!-- 组头行：整组批量。受管态 = amber 淡底 + 左竖条 + 「整组」标 -->
        <div class="ct-row ct-grouphead" :class="{ managed: groupManaged(g) }">
          <button type="button" class="ct-gname" :aria-expanded="expanded[g.key]" @click="toggleGroup(g.key)">
            <span class="chev" :class="{ open: expanded[g.key] }">▸</span>{{ g.label }}
            <!-- 诚实的「整组」标：有单独设置时带例外计数；组未管但有单独时给弱化计数 -->
            <span v-if="groupManaged(g)" class="grp-tag" :class="{ mixed: overriddenLeaves(g) > 0 }">整组{{ overriddenLeaves(g) ? ' · ' + overriddenLeaves(g) + ' 单独' : '' }}</span>
            <span v-else-if="overriddenLeaves(g)" class="grp-count">{{ overriddenLeaves(g) }} 单独</span>
          </button>
          <div class="ct-cell">
            <SwitchRoot v-if="!g.isFlat && groupConfigurable(g)" class="pw-switch sm"
              :model-value="groupEff(g)" :aria-label="g.label + ' 整组' + colHead"
              @update:model-value="(v: boolean) => onGroupToggle(g, v)">
              <SwitchThumb class="pw-switch-thumb" />
            </SwitchRoot>
            <span v-else-if="!g.isFlat" class="ct-na">—</span>
          </div>
        </div>

        <!-- 叶子行：开关显示生效值；单独设置 = 名旁圆点 + amber 环 + ↺ -->
        <template v-if="expanded[g.key]">
          <div v-for="n in g.nodes" :key="n.path" class="ct-row ct-leaf"
            :class="{ danger: isEnabledAxis && n.danger, overridden: configurable(n) && hasAxisOverride(n.path), grouped: configurable(n) && groupManaged(g) && !hasAxisOverride(n.path) && !(isEnabledAxis && n.danger) }">
            <div class="ct-lname">
              <span class="lbl">{{ n.label }}
                <!-- 危险标只在功能页（enabled 轴）有信息量：不随整组、需逐条开启；权限页该三条恒锁定，标是噪音 -->
                <span v-if="isEnabledAxis && n.danger" class="dtag" title="危险命令：不随整组开关，需逐条开启">危险</span>
                <span v-if="configurable(n) && hasAxisOverride(n.path)" class="ov-dot" title="此命令已单独设置" aria-label="已单独设置"></span>
              </span>
              <span class="path mono">/pal {{ n.path }}</span>
            </div>
            <div class="ct-cell">
              <span v-if="lockedLabel(n)" class="ct-lock">{{ lockedLabel(n) }}<small>内置</small></span>
              <SwitchRoot v-else class="pw-switch sm" :class="{ ovr: hasAxisOverride(n.path) }"
                :model-value="effOf(n)" :aria-label="n.label + ' ' + colHead"
                @update:model-value="(v: boolean) => onLeafToggle(n, v)">
                <SwitchThumb class="pw-switch-thumb" />
              </SwitchRoot>
            </div>
          </div>
        </template>
      </div>
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
/* 受管态（整组批量生效中）：focus 蓝淡底 + 左竖条（Unity override bar / GitHub managed 语义）。
   覆盖/受管统一用 focus 蓝（「你设置过的」）——绿=状态、蓝=覆盖、红=危险，amber 留给主动作。 */
.ct-grouphead.managed { background: color-mix(in srgb, var(--override) 24%, var(--sink)); box-shadow: inset 3px 0 0 var(--override); }
.ct-grouphead.managed .ct-gname { color: var(--override); }
/* 非纯整组（有叶子单独设置）：title 行底/竖条换 warn 琥珀系，与纯整组一眼区分 */
.ct-group.mixed .ct-grouphead.managed { background: color-mix(in srgb, var(--warn) 22%, var(--sink)); box-shadow: inset 3px 0 0 var(--warn); }
.ct-group.mixed .ct-grouphead.managed .ct-gname { color: var(--warn); }
.ct-gname { flex: 1; display: flex; align-items: center; gap: var(--space-2); font-family: var(--sans); font-size: var(--fs-sm); font-weight: var(--fw-semibold); color: var(--ink); background: none; border: none; cursor: pointer; text-align: left; padding: 0; }
.ct-gname .chev { display: inline-block; font-size: var(--fs-caption); color: var(--ink-3); transition: transform var(--motion-fast); }
.ct-gname .chev.open { transform: rotate(90deg); }
.ct-gname:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: var(--r-sm); }
.grp-tag { font-size: var(--fs-caption); font-weight: var(--fw-semibold); color: var(--on-override); background: var(--override); border: none; border-radius: var(--r-pill); padding: 1px var(--space-2); }
/* 非纯整组（有叶子单独设置）：warn 琥珀标——一眼区分「纯整组」与「混合管控」 */
.grp-tag.mixed { color: var(--on-warn); background: var(--warn); }
.grp-count { font-size: var(--fs-caption); font-weight: var(--fw-regular); color: var(--ink-3); }

.ct-leaf { border-top: 1px dashed var(--rule); }
/* 随组叶子：淡一档 focus 左竖条贯穿受管区块 */
.ct-leaf.grouped { box-shadow: inset 3px 0 0 var(--override); background: color-mix(in srgb, var(--override) 8%, transparent); }
/* 单独设置的行（组开没开都算）：同系底色稍深一档 + 竖条；危险行红竖条优先（下方规则覆盖） */
.ct-leaf.overridden { box-shadow: inset 3px 0 0 var(--override); background: color-mix(in srgb, var(--override) 12%, transparent); }
/* 危险行（enabled 轴）：行首细红边；不随组开关（后端 F2）→ 永不加 amber 竖条 */
.ct-leaf.danger { box-shadow: inset 2px 0 0 var(--danger); }
.ct-lname { flex: 1; display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ct-lname .lbl { font-size: var(--fs-caption); color: var(--ink); display: flex; align-items: center; gap: var(--space-2); }
.ct-lname .path { font-size: var(--fs-caption); color: var(--ink-3); }
.dtag { font-size: var(--fs-caption); font-weight: var(--fw-medium); color: var(--danger); border: 1px solid color-mix(in srgb, var(--danger) 55%, transparent); background: color-mix(in srgb, var(--danger) 8%, transparent); border-radius: var(--r-sm); padding: 0 var(--space-1); }
/* 单独设置标识：override 圆点（行名旁）+ 开关外环（明=靛蓝，暗=青） */
.ov-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--override); flex: 0 0 auto; }
.pw-switch.ovr { box-shadow: 0 0 0 2px var(--override); }

.ct-cell { width: 120px; display: flex; align-items: center; justify-content: flex-end; flex: none; }
.ct-na { color: var(--ink-3); font-size: var(--fs-caption); }

.ct-lock { display: inline-flex; align-items: baseline; gap: var(--space-1); font-size: var(--fs-caption); color: var(--ink-3); font-style: normal; }
.ct-lock small { font-size: var(--fs-caption); color: var(--ink-3); opacity: .75; border: 1px solid var(--rule-2); border-radius: var(--r-sm); padding: 0 var(--space-1); }
</style>

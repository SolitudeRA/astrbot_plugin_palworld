<script setup lang="ts">
import { SwitchRoot, SwitchThumb } from 'reka-ui'
import { PAL_TREE, type PalTreeNode } from '../lib/schema'
import type { CmdPerm } from '../lib/collect'
import { FEATURES, featureAgg, setFeature, effEnabled, type FeatureSpec, type FeatureAgg } from '../lib/permissions'

const props = defineProps<{ modelValue: Record<string, CmdPerm> }>()
const emit = defineEmits<{ 'update:modelValue': [v: Record<string, CmdPerm>]; change: [] }>()

const NODE_BY_PATH: Record<string, PalTreeNode> = Object.fromEntries(PAL_TREE.map((n) => [n.path, n]))
const nodeOf = (path: string) => NODE_BY_PATH[path]

const aggOf = (f: FeatureSpec): FeatureAgg => featureAgg(props.modelValue, f, nodeOf)
// mixed（成员被单独设置导致不一致）时开关按「开」显示，配「部分开启」标；操作即收编统一
const checkedOf = (f: FeatureSpec) => aggOf(f) !== 'off'
const enabledCount = (f: FeatureSpec) =>
  f.memberPaths.filter((p) => effEnabled(props.modelValue, nodeOf(p))).length

function onToggle(f: FeatureSpec, target: boolean) {
  emit('update:modelValue', setFeature(props.modelValue, f, target))
  emit('change')
}
</script>

<template>
  <section class="feature-panel">
    <div class="group-head"><span class="t">功能开关</span><span class="c">决定机器人开放哪些查询与操作</span></div>
    <p class="grouphint">关闭的功能其命令不可用。谁能使用哪些命令，在「权限」页设置。</p>
    <div class="fp-board">
      <div v-for="f in FEATURES" :key="f.key" class="row fp-row" :data-feat="f.key">
        <div class="rlabel">
          {{ f.label }}<span v-if="f.danger" class="fp-danger">危险</span>
          <small>{{ f.hint }}</small>
        </div>
        <div class="rctl">
          <span v-if="aggOf(f) === 'mixed'" class="fp-mixed" :title="`${enabledCount(f)}/${f.memberPaths.length} 条命令开启（有命令被单独设置）`">部分开启</span>
          <SwitchRoot class="pw-switch" :model-value="checkedOf(f)" :aria-label="f.label"
            @update:model-value="(v: boolean) => onToggle(f, v)">
            <SwitchThumb class="pw-switch-thumb" />
          </SwitchRoot>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.feature-panel { display: flex; flex-direction: column; }
.fp-board { background: var(--card); border: 1px solid var(--rule); border-radius: var(--r); padding: var(--space-1) var(--space-4); margin-top: var(--space-2); }
.fp-row:last-child { border-bottom: none; }
.fp-danger { font-size: var(--fs-caption); font-weight: var(--fw-medium); color: var(--danger); border: 1px solid color-mix(in srgb, var(--danger) 55%, transparent); background: color-mix(in srgb, var(--danger) 8%, transparent); border-radius: var(--r-sm); padding: 0 var(--space-1); margin-left: var(--space-2); }
.fp-mixed { font-size: var(--fs-caption); font-weight: var(--fw-medium); color: var(--amber); border: 1px solid color-mix(in srgb, var(--amber) 45%, transparent); background: color-mix(in srgb, var(--amber) 8%, transparent); border-radius: var(--r-pill); padding: 1px var(--space-2); margin-right: var(--space-3); }
</style>

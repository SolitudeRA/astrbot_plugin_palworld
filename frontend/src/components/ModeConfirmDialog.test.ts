import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ModeConfirmDialog from './ModeConfirmDialog.vue'

describe('ModeConfirmDialog', () => {
  it('target=multi：allowed_groups 全默认勾，确认 emit 全部 umo', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'multi',
      preview: { ok: true, ready_servers: [{ server_id: 'a', name: 'a' }],
        allowed_groups: [{ umo: 'u1', note: '主群' }, { umo: 'u2', note: '' }] },
    } })
    expect(w.text()).toContain('切换到多服务器')
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toEqual(['u1', 'u2'])
  })

  it('target=single：已有保留台权限默认勾、将获新权默认不勾', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'single', survivingId: 'keep',
      preview: { ok: true, ready_servers: [{ server_id: 'keep', name: 'keep' }],
        bindings: [{ umo: 'u_has', server_ids: ['keep', 'x'] }, { umo: 'u_new', server_ids: ['x'] }] },
    } })
    // u_has 已有权 → 默认勾；u_new 将获新权 → 默认不勾
    expect(w.text()).toContain('已有权')
    expect(w.text()).toContain('将获新权')
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toEqual(['u_has'])
  })

  it('target=single：手动勾上「将获新权」→ 确认含该 umo（扩权）', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'single', survivingId: 'keep',
      preview: { ok: true, ready_servers: [{ server_id: 'keep', name: 'keep' }],
        bindings: [{ umo: 'u_new', server_ids: ['x'] }] },
    } })
    const boxes = w.findAll('input[type="checkbox"]')
    await boxes[0].setValue(true)
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toEqual(['u_new'])
  })

  it('取消全部勾选 → 显示未迁移告警', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'multi', preview: { ok: true, ready_servers: [{ server_id: 'a', name: 'a' }],
        allowed_groups: [{ umo: 'u1', note: '' }] },
    } })
    await w.findAll('input[type="checkbox"]')[0].setValue(false)
    expect(w.text()).toContain('未勾选任何群')
  })

  it('target=multi 且无就绪台 → 提示无可绑目标', () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'multi', preview: { ok: true, ready_servers: [], allowed_groups: [{ umo: 'u1', note: '' }] },
    } })
    expect(w.text()).toContain('无就绪服务器可绑定')
  })

  it('cancel 按钮 emit cancel', async () => {
    const w = mount(ModeConfirmDialog, { props: {
      target: 'multi', preview: { ok: true, ready_servers: [{ server_id: 'a', name: 'a' }], allowed_groups: [] },
    } })
    await w.get('button[data-act="cancel"]').trigger('click')
    expect(w.emitted('cancel')).toBeTruthy()
  })
})

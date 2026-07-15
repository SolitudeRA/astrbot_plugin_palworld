import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TransferWizard from './TransferWizard.vue'

const preview = {
  ok: true,
  ready_servers: [{ server_id: 'keep', name: 'keep' }, { server_id: 'other', name: 'other' }],
  bindings: [{ umo: 'u_has', server_ids: ['keep'] }, { umo: 'u_new', server_ids: ['other'] }],
}
// serverNames 含一个非就绪台 ghost（不在 ready_servers）→ 删除台数须含它（M-c）
const serverNames = ['keep', 'other', 'ghost']

const mk = () => mount(TransferWizard, { props: { preview, serverNames } })

describe('TransferWizard', () => {
  it('步1 选保留台后可下一步；步2 已有权默认勾、将获新权默认不勾', async () => {
    const w = mk()
    // 步1：选 keep
    await w.findAll('input[type="radio"]')[0].setValue() // 第一个 radio = keep
    await w.get('button[data-act="next"]').trigger('click')
    // 步2：u_has(已有 keep 权)默认勾、u_new(仅 other)默认不勾
    const boxes = w.findAll('input[type="checkbox"]')
    expect((boxes[0].element as HTMLInputElement).checked).toBe(true) // u_has
    expect((boxes[1].element as HTMLInputElement).checked).toBe(false) // u_new
  })

  it('删除侧：摘要页勾选闸勾选前确认禁用、勾选后启用；删除台数含非就绪 ghost', async () => {
    const w = mk()
    await w.findAll('input[type="radio"]')[0].setValue() // 选 keep
    await w.get('button[data-act="next"]').trigger('click') // → 步2
    await w.get('button[data-act="next"]').trigger('click') // → 步3
    // 步3：选「删除其余」
    const step3Radios = w.findAll('input[type="radio"]')
    await step3Radios[step3Radios.length - 1].setValue() // 删除选项
    await w.get('button[data-act="next"]').trigger('click') // → 步4 摘要
    // 删除台数 = serverNames − surviving = other + ghost = 2（含非就绪 ghost）
    expect(w.text()).toContain('2')
    expect(w.text()).toContain('ghost')
    // 勾选闸前禁用
    const confirmBtn = w.get('button[data-act="confirm"]')
    expect((confirmBtn.element as HTMLButtonElement).disabled).toBe(true)
    await w.get('input[data-act="ack"]').setValue(true)
    expect((confirmBtn.element as HTMLButtonElement).disabled).toBe(false)
  })

  it('删除侧确认 → emit payload（purge_others=true、含勾选迁移群）', async () => {
    const w = mk()
    await w.findAll('input[type="radio"]')[0].setValue()
    await w.get('button[data-act="next"]').trigger('click')
    await w.get('button[data-act="next"]').trigger('click')
    const step3Radios = w.findAll('input[type="radio"]')
    await step3Radios[step3Radios.length - 1].setValue() // 删除
    await w.get('button[data-act="next"]').trigger('click')
    await w.get('input[data-act="ack"]').setValue(true)
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toEqual({
      surviving_server_id: 'keep', migrate_umos: ['u_has'], purge_others: true,
    })
  })

  it('保留侧：无需勾选闸即可确认，purge_others=false', async () => {
    const w = mk()
    await w.findAll('input[type="radio"]')[0].setValue()
    await w.get('button[data-act="next"]').trigger('click')
    await w.get('button[data-act="next"]').trigger('click')
    const step3Radios = w.findAll('input[type="radio"]')
    await step3Radios[step3Radios.length - 2].setValue() // 保留选项
    await w.get('button[data-act="next"]').trigger('click')
    expect((w.get('button[data-act="confirm"]').element as HTMLButtonElement).disabled).toBe(false)
    await w.get('button[data-act="confirm"]').trigger('click')
    expect(w.emitted('confirm')?.[0]?.[0]).toMatchObject({ surviving_server_id: 'keep', purge_others: false })
  })

  it('cancel emit cancel', async () => {
    const w = mk()
    await w.get('button[data-act="cancel"]').trigger('click')
    expect(w.emitted('cancel')).toBeTruthy()
  })

  // FIX 2：步3「删除→保留→删除」切换须复位 deleteAck，回到删除时确认闸重新要求勾选（不复用旧勾）
  it('步3 删除→保留→删除 → deleteAck 复位、确认按钮再次禁用', async () => {
    const w = mk()
    await w.findAll('input[type="radio"]')[0].setValue() // 选 keep
    await w.get('button[data-act="next"]').trigger('click') // → 步2
    await w.get('button[data-act="next"]').trigger('click') // → 步3
    let radios = w.findAll('input[type="radio"]')
    await radios[radios.length - 1].setValue() // 删除
    await w.get('button[data-act="next"]').trigger('click') // → 步4
    await w.get('input[data-act="ack"]').setValue(true) // 勾选确认
    expect((w.get('button[data-act="confirm"]').element as HTMLButtonElement).disabled).toBe(false)
    // 回步3 → 切保留 → 再切删除
    await w.get('button[data-act="back"]').trigger('click') // → 步3
    radios = w.findAll('input[type="radio"]')
    await radios[radios.length - 2].setValue() // 保留（触发 watch 复位 ack）
    await radios[radios.length - 1].setValue() // 再删除
    await w.get('button[data-act="next"]').trigger('click') // → 步4
    // ack 已复位 → 销毁性操作确认闸再次要求勾选
    expect((w.vm as any).deleteAck).toBe(false)
    expect((w.get('button[data-act="confirm"]').element as HTMLButtonElement).disabled).toBe(true)
  })

  // FIX 6：改选保留台后，步2 迁移默认勾按新台重算（已有权/将获新权在 A、B 间翻转）
  it('改选保留台 → 步2 勾选默认按新台重算（已有/新权翻转）', async () => {
    const w = mk()
    // 选 keep：u_has(含 keep)默认勾、u_new(仅 other)默认不勾
    await w.findAll('input[type="radio"]')[0].setValue() // keep
    await w.get('button[data-act="next"]').trigger('click')
    let boxes = w.findAll('input[type="checkbox"]')
    expect((boxes[0].element as HTMLInputElement).checked).toBe(true)  // u_has 已有权@keep
    expect((boxes[1].element as HTMLInputElement).checked).toBe(false) // u_new 将获新权@keep
    // 回步1 → 改选 other：翻转
    await w.get('button[data-act="back"]').trigger('click')
    await w.findAll('input[type="radio"]')[1].setValue() // other
    await w.get('button[data-act="next"]').trigger('click')
    boxes = w.findAll('input[type="checkbox"]')
    expect((boxes[0].element as HTMLInputElement).checked).toBe(false) // u_has 将获新权@other
    expect((boxes[1].element as HTMLInputElement).checked).toBe(true)  // u_new 已有权@other
  })
})
